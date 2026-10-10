"""Strict parsing of the seven official, versioned O*NET CSV source files."""

import csv
import gzip
import hashlib
import json
import os
import re
import tempfile
import time
import zlib
from contextlib import ExitStack, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from shutil import rmtree
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx

FILES = (
    "occupation_data.csv",
    "job_titles.csv",
    "content_model_reference.csv",
    "essential_skills.csv",
    "transferable_skills.csv",
    "software_skills.csv",
    "scales_reference.csv",
)
RATED_HEADERS = (
    "O*NET-SOC Code",
    "Title",
    "Element ID",
    "Element Name",
    "Scale ID",
    "Scale Name",
    "Data Value",
    "N",
    "Standard Error",
    "Lower CI Bound",
    "Upper CI Bound",
    "Recommend Suppress",
    "Not Relevant",
    "Date",
    "Domain Source",
)
HEADERS = {
    "occupation_data.csv": ("O*NET-SOC Code", "Title", "Description"),
    "job_titles.csv": (
        "O*NET-SOC Code",
        "Title",
        "Job Title",
        "Short Title",
        "Source(s)",
    ),
    "content_model_reference.csv": ("Element ID", "Element Name", "Description"),
    "essential_skills.csv": RATED_HEADERS,
    "transferable_skills.csv": RATED_HEADERS,
    "software_skills.csv": (
        "O*NET-SOC Code",
        "Title",
        "Workplace Example",
        "Element ID",
        "Element Name",
        "Hot Technology",
        "In Demand",
    ),
    "scales_reference.csv": ("Scale ID", "Scale Name", "Minimum", "Maximum"),
}
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATABASE_URL = "https://www.onetcenter.org/database.html"
MAX_FILE_BYTES = 250 * 1024 * 1024


def release_url(release: str, filename: str) -> str:
    if re.fullmatch(r"\d+\.\d+", release) is None or filename not in FILES:
        raise ValueError("Unsupported O*NET release or file")
    return (
        "https://www.onetcenter.org/dl_files/database/"
        f"db_{release.replace('.', '_')}_csv/{filename}"
    )


def attribution(release: str) -> str:
    return (
        f"Contains information from O*NET® Database {release}, by the U.S. "
        "Department of Labor, Employment and Training Administration (USDOL/ETA). "
        "Used under CC BY 4.0. Lab Tutor filters, maps and may rephrase skills; "
        "source ratings are retained. "
        f"Source: {DATABASE_URL}. License: {LICENSE_URL}."
    )


def source_key(
    release: str,
    soc_code: str,
    family: str,
    element_id: str,
    workplace_example: str = "",
) -> str:
    return json.dumps(
        [release, soc_code, family, element_id, workplace_example],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def source_record_id(
    release: str,
    soc_code: str,
    family: str,
    element_id: str,
    workplace_example: str = "",
) -> str:
    key = source_key(release, soc_code, family, element_id, workplace_example)
    return str(uuid5(NAMESPACE_URL, "https://www.onetcenter.org/" + key))


@dataclass
class ParsedOccupation:
    soc_code: str
    title: str
    description: str
    alternate_titles: list[str] = field(default_factory=list)
    source_rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class ParsedEvidence:
    id: str
    release: str
    soc_code: str
    family: str
    element_id: str
    label: str
    definition: str
    workplace_example: str | None
    ratings: dict[str, dict[str, Any]]
    flags: dict[str, bool | None]
    source_rows: list[dict[str, str]]
    source_key: str


@dataclass
class ParsedRelease:
    version: str
    occupations: list[ParsedOccupation]
    evidence: list[ParsedEvidence]
    manifest: dict[str, Any]

    @property
    def attribution(self) -> str:
        return attribution(self.version)


def _read_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != HEADERS[path.name]:
                raise ValueError(f"Invalid O*NET header in {path.name}")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Malformed O*NET row in {path.name}")
                rows.append(row)
            return rows
    except (OSError, csv.Error, UnicodeError) as exc:
        raise ValueError(f"Invalid O*NET CSV in {path.name}") from exc


def _required(raw: str, label: str) -> str:
    if not raw.strip():
        raise ValueError(f"O*NET {label} must be nonempty")
    return raw


def _number(raw: str, *, minimum: float, maximum: float = float("inf")) -> float | None:
    if not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("Invalid O*NET numeric value") from exc
    if not isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("O*NET number is outside its declared range")
    return value


def parse_rating_value(raw: str, minimum: float, maximum: float) -> float | None:
    return _number(raw, minimum=minimum, maximum=maximum)


def _flag(raw: str, *, optional: bool = False) -> bool | None:
    if raw == "Y":
        return True
    if raw == "N":
        return False
    if raw == "":
        return None if optional else False
    raise ValueError("O*NET flags must be Y, N or blank")


def _date(raw: str) -> str | None:
    if not raw:
        return None
    if re.fullmatch(r"(0[1-9]|1[0-2])/[1-9]\d{3}", raw) is None:
        raise ValueError("Invalid O*NET month/year date")
    return raw


def _unique(rows: list[dict[str, str]], column: str) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        key = _required(row[column], column)
        if key in result:
            raise ValueError(f"Conflicting O*NET duplicate {column}")
        result[key] = row
    return result


def _rating(row: dict[str, str], scales: dict[str, dict[str, str]]) -> dict[str, Any]:
    scale_id = row["Scale ID"]
    if scale_id not in {"IM", "LV"} or scale_id not in scales:
        raise ValueError("Unknown O*NET rating scale")
    scale = scales[scale_id]
    minimum, maximum = float(scale["Minimum"]), float(scale["Maximum"])
    if (minimum, maximum) != {"IM": (1, 5), "LV": (0, 7)}[scale_id]:
        raise ValueError("Unexpected O*NET rating scale bounds")
    if row["Scale Name"] != scale["Scale Name"]:
        raise ValueError("Conflicting O*NET scale name")
    n = _number(row["N"], minimum=0)
    if n is not None and not n.is_integer():
        raise ValueError("O*NET N must be an integer")
    lower = parse_rating_value(row["Lower CI Bound"], minimum, maximum)
    upper = parse_rating_value(row["Upper CI Bound"], minimum, maximum)
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("O*NET confidence interval bounds are reversed")
    value = parse_rating_value(row["Data Value"], minimum, maximum)
    suppressed = _flag(row["Recommend Suppress"], optional=True)
    not_relevant = _flag(row["Not Relevant"], optional=True)
    status = (
        "suppressed"
        if suppressed
        else "not_relevant"
        if not_relevant
        else "missing"
        if value is None
        else "reported"
    )
    return {
        "scale_id": scale_id,
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "status": status,
        "date": _date(row["Date"]),
        "quality": {
            key: row[key]
            for key in (
                "N",
                "Standard Error",
                "Lower CI Bound",
                "Upper CI Bound",
                "Recommend Suppress",
                "Not Relevant",
                "Domain Source",
            )
        },
    }


def _file_manifest(path: Path, release: str, row_count: int) -> dict[str, Any]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "url": release_url(release, path.name),
        "sha256": digest,
        "bytes": path.stat().st_size,
        "row_count": row_count,
    }


def parse_release(directory: Path, release: str) -> ParsedRelease:
    release_url(release, FILES[0])
    tables = {name: _read_rows(directory / name) for name in FILES}
    occupations = _unique(tables["occupation_data.csv"], "O*NET-SOC Code")
    definitions = _unique(tables["content_model_reference.csv"], "Element ID")
    scales = _unique(tables["scales_reference.csv"], "Scale ID")
    for row in definitions.values():
        _required(row["Element Name"], "element name")
    for row in scales.values():
        _required(row["Scale Name"], "scale name")
        low = _number(_required(row["Minimum"], "scale minimum"), minimum=-float("inf"))
        high = _number(
            _required(row["Maximum"], "scale maximum"), minimum=-float("inf")
        )
        if low > high:
            raise ValueError("Invalid O*NET scale bounds")
    catalog = {}
    for soc, row in occupations.items():
        if re.fullmatch(r"\d{2}-\d{4}\.\d{2}", soc) is None:
            raise ValueError("Invalid O*NET occupation code")
        catalog[soc] = ParsedOccupation(
            soc,
            _required(row["Title"], "occupation title"),
            row["Description"],
            source_rows=[row],
        )
    title_rows = {}
    for row in tables["job_titles.csv"]:
        occupation = catalog.get(row["O*NET-SOC Code"])
        if occupation is None:
            raise ValueError("Unknown O*NET occupation in job titles")
        _required(row["Job Title"], "job title")
        title_key = (row["O*NET-SOC Code"], row["Job Title"])
        if title_key in title_rows:
            raise ValueError("Conflicting O*NET duplicate job title")
        title_rows[title_key] = row
        occupation.source_rows.append(row)
        for alias in (row["Job Title"], row["Short Title"]):
            if alias and alias not in occupation.alternate_titles:
                occupation.alternate_titles.append(alias)
    evidence: dict[str, ParsedEvidence] = {}
    duplicate_rows = {}
    for family in ("essential", "transferable", "software"):
        for row in tables[f"{family}_skills.csv"]:
            soc, element = row["O*NET-SOC Code"], row["Element ID"]
            if soc not in catalog or element not in definitions:
                raise ValueError("Unknown O*NET occupation or element reference")
            _required(row["Title"], "occupation title")
            label = _required(row["Element Name"], "element name")
            example = (
                _required(row["Workplace Example"], "workplace example")
                if family == "software"
                else ""
            )
            key = source_key(release, soc, family, element, example)
            row_key = (key, row.get("Scale ID", ""))
            if row_key in duplicate_rows:
                raise ValueError("Conflicting O*NET duplicate source row")
            duplicate_rows[row_key] = row
            item = evidence.get(key)
            if item is None:
                item = ParsedEvidence(
                    source_record_id(release, soc, family, element, example),
                    release,
                    soc,
                    family,
                    element,
                    label,
                    definitions[element]["Description"],
                    example or None,
                    {},
                    {},
                    [],
                    key,
                )
                evidence[key] = item
            if label != item.label:
                raise ValueError("Conflicting O*NET element label")
            if family == "software":
                item.flags = {
                    "Hot Technology": _flag(row["Hot Technology"], optional=True),
                    "In Demand": _flag(row["In Demand"], optional=True),
                }
            else:
                item.ratings[row["Scale ID"]] = _rating(row, scales)
            item.source_rows.append(row)
    manifest = {
        "version": release,
        "files": {
            name: _file_manifest(directory / name, release, len(tables[name]))
            for name in FILES
        },
        "source_url": DATABASE_URL,
        "license_url": LICENSE_URL,
        "attribution": attribution(release),
    }
    return ParsedRelease(
        release, list(catalog.values()), list(evidence.values()), manifest
    )


def manifest_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    """Ignore retrieval times and calculated summaries when comparing content."""
    return {
        "version": manifest["version"],
        "files": {
            name: {"url": f["url"], "sha256": f["sha256"]}
            for name, f in manifest["files"].items()
        },
    }


class _RetryDownload(Exception):
    def __init__(self, status: int, retry_after: str | None):
        self.status = status
        self.retry_after = retry_after


def _download_file(url: str, path: Path, client: httpx.Client) -> None:
    with ExitStack() as stack:
        for redirect in range(4):
            response = stack.enter_context(
                client.stream(
                    "GET",
                    url,
                    follow_redirects=False,
                    timeout=httpx.Timeout(60, connect=10),
                    headers={"Accept-Encoding": "identity", "Accept": "text/csv"},
                )
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            next_url = urljoin(url, response.headers.get("Location", ""))
            target = urlsplit(next_url)
            if (
                redirect == 3
                or target.scheme != "https"
                or target.hostname != "www.onetcenter.org"
                or target.port not in {None, 443}
                or target.username is not None
            ):
                raise ValueError("Unsafe O*NET redirect")
            response.close()
            url = next_url
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            raise _RetryDownload(
                response.status_code, response.headers.get("Retry-After")
            )
        if response.status_code != 200:
            raise ValueError(f"O*NET download returned HTTP {response.status_code}")
        if response.headers.get("Content-Type", "").split(";", 1)[0].lower() not in {
            "text/csv",
            "text/plain",
            "application/csv",
            "application/octet-stream",
        }:
            raise ValueError("O*NET download returned HTML")
        content_length = response.headers.get("Content-Length")
        try:
            declared = int(content_length) if content_length is not None else None
        except ValueError as exc:
            raise ValueError("Invalid O*NET Content-Length") from exc
        if declared is not None and (declared < 0 or declared > MAX_FILE_BYTES):
            raise ValueError("O*NET file exceeds size limit")
        encoding = response.headers.get("Content-Encoding", "").strip().lower()
        if encoding not in {"", "identity", "gzip"}:
            raise ValueError("Unsupported O*NET download content encoding")
        if encoding == "gzip" and response.is_stream_consumed:
            raise ValueError("O*NET gzip response must provide its raw stream")
        wire_path = path.with_suffix(".gzip.part") if encoding == "gzip" else path
        if encoding == "gzip":
            # Raw reads can fail before decompression begins, and a retry may
            # return identity encoding. Never carry wire staging into that retry.
            stack.callback(wire_path.unlink, missing_ok=True)
        wire_bytes = 0
        chunks = (
            (response.content,) if response.is_stream_consumed else response.iter_raw()
        )
        with wire_path.open("wb") as stream:
            for chunk in chunks:
                wire_bytes += len(chunk)
                if wire_bytes > MAX_FILE_BYTES:
                    raise ValueError("O*NET file exceeds size limit")
                stream.write(chunk)
        if declared is not None and wire_bytes != declared:
            raise ValueError("Truncated O*NET download")
        if encoding == "gzip":
            try:
                # gzip checks EOF, CRC and original size for every member. HTTPX
                # decoding alone may emit a complete CSV prefix without a footer.
                size = 0
                with (
                    gzip.open(wire_path, "rb") as compressed,
                    path.open("wb") as decoded,
                ):
                    while chunk := compressed.read(64 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise ValueError("O*NET decoded file exceeds size limit")
                        decoded.write(chunk)
            except (EOFError, gzip.BadGzipFile, zlib.error) as exc:
                raise ValueError("Invalid or incomplete O*NET gzip stream") from exc
    _read_rows(path)


def download_release(release: str, cache_dir: Path, client: httpx.Client) -> Path:
    """Install a validated release cache only after every file succeeds."""
    release_url(release, FILES[0])
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / release
    if destination.is_symlink():
        raise ValueError("O*NET release cache cannot be a symlink")
    staging = Path(tempfile.mkdtemp(prefix=f".{release}-", dir=cache_dir))
    delay_used = 0.0
    try:
        for filename in FILES:
            part = staging / filename
            for attempt in range(3):
                try:
                    _download_file(release_url(release, filename), part, client)
                    break
                except (httpx.TransportError, _RetryDownload) as exc:
                    part.unlink(missing_ok=True)
                    if attempt == 2:
                        status = (
                            f"HTTP {exc.status}"
                            if isinstance(exc, _RetryDownload)
                            else "transport failure"
                        )
                        raise ValueError(
                            f"O*NET download failed after 3 attempts: {status}"
                        ) from exc
                    requested = 2**attempt
                    if isinstance(exc, _RetryDownload) and exc.retry_after:
                        with suppress(ValueError):
                            requested = float(exc.retry_after)
                    if not isfinite(requested):
                        requested = 2**attempt
                    delay = max(0, min(requested, 10 - delay_used))
                    time.sleep(delay)
                    delay_used += delay
        parsed = parse_release(staging, release)
        manifest = {**parsed.manifest, "retrieved_at": datetime.now(UTC).isoformat()}
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if destination.exists():
            cached = parse_release(destination, release)
            try:
                stored = json.loads(
                    (destination / "manifest.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise ValueError("Incomplete O*NET cached release manifest") from exc
            if manifest_identity(cached.manifest) != manifest_identity(
                stored
            ) or manifest_identity(cached.manifest) != manifest_identity(manifest):
                raise ValueError(
                    f"O*NET release {release} has different source content"
                )
            return destination
        os.rename(staging, destination)
        return destination
    finally:
        rmtree(staging, ignore_errors=True)
