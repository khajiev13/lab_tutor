"""Synchronous public vacancy API adapter with bounded, credential-safe failures."""

import contextlib
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.marketdemandanalyst.schemas import (
    ProviderVacancy,
    safe_provider_payload,
)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif not self.hidden and tag in {
            "p",
            "li",
            "br",
            "div",
            "h1",
            "h2",
            "h3",
            "tr",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {"p", "li", "div", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = _TextParser()
    parser.feed(value)
    return "\n".join(
        line.strip() for line in "".join(parser.parts).splitlines() if line.strip()
    )


class _Employer(BaseModel):
    name: str = ""


class _Item(BaseModel):
    id: str
    employer: _Employer | None = None


class _Page(BaseModel):
    items: list[_Item]
    pages: int = Field(ge=0, strict=True)


class _Area(BaseModel):
    name: str = ""


class _Tag(BaseModel):
    name: str | None = None


class _Detail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    employer: _Employer | None = None
    area: _Area | None = None
    description: str
    alternate_url: str
    key_skills: list[_Tag] = Field(default_factory=list)
    archived: bool = False


class HeadHunterSearchResult(BaseModel):
    jobs: list[ProviderVacancy] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class _ProviderError(ValueError):
    pass


class _RemovedVacancy(_ProviderError):
    pass


class HeadHunterService:
    def __init__(self, *, client: httpx.Client, user_agent: str, access_token: str):
        self._client = client
        self._user_agent = user_agent.strip()
        self._access_token = access_token.strip()

    def _request(self, path: str, params: dict) -> dict:
        delay_spent = 0.0
        for attempt in range(3):
            response = None
            with contextlib.suppress(httpx.TransportError):
                response = self._client.get(
                    f"https://api.hh.ru{path}",
                    params={"host": "hh.uz", **params},
                    headers={
                        "HH-User-Agent": self._user_agent,
                        "User-Agent": self._user_agent,
                        "Authorization": f"Bearer {self._access_token}",
                    },
                    timeout=httpx.Timeout(15, connect=5),
                    follow_redirects=False,
                )
            if response is not None:
                if response.status_code == 404:
                    raise _RemovedVacancy(
                        "A vacancy was removed before its details could be collected."
                    )
                if response.status_code not in {429, 500, 502, 503, 504}:
                    if response.status_code != 200:
                        raise _ProviderError(
                            "HeadHunter rejected the request; check provider access."
                        )
                    try:
                        payload = response.json()
                    except ValueError:
                        raise _ProviderError(
                            "HeadHunter returned an invalid response."
                        ) from None
                    if not isinstance(payload, dict):
                        raise _ProviderError("HeadHunter returned an invalid response.")
                    return safe_provider_payload(payload, self._access_token)
            if attempt == 2:
                break
            delay = float(2**attempt)
            retry_after = (
                response.headers.get("Retry-After") if response is not None else None
            )
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        retry_date = parsedate_to_datetime(retry_after)
                        delay = (retry_date - datetime.now(UTC)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        raise _ProviderError(
                            "HeadHunter retry instructions were invalid."
                        ) from None
            if not 0 <= delay <= 5 - delay_spent:
                raise _ProviderError("HeadHunter is rate limited; retry later.")
            time.sleep(delay)
            delay_spent += delay
        raise _ProviderError("HeadHunter could not complete the request; retry later.")

    def search_jobs(
        self,
        search_term: str,
        *,
        area_id: str,
        results_wanted: int,
        hours_old: int = 72,
    ) -> HeadHunterSearchResult:
        if (
            not search_term.strip()
            or not isinstance(results_wanted, int)
            or isinstance(results_wanted, bool)
            or not 1 <= results_wanted <= 100
            or hours_old <= 0
        ):
            raise ValueError(
                "A query, positive time range, and result cap from 1 to 100 are required"
            )
        result = HeadHunterSearchResult()
        if not self._user_agent or not self._access_token:
            result.error = "HeadHunter is not configured."
            return result
        seen = set()
        date_from = (datetime.now(UTC) - timedelta(hours=hours_old)).strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )
        page = 0
        try:
            while page * results_wanted < 2000:
                data = _Page.model_validate(
                    self._request(
                        "/vacancies",
                        {
                            "text": search_term.strip(),
                            "area": area_id,
                            "per_page": results_wanted,
                            "page": page,
                            "date_from": date_from,
                        },
                    )
                )
                for item in data.items:
                    if item.id in seen:
                        continue
                    if not item.id.isdigit():
                        raise _ProviderError(
                            "HeadHunter returned an invalid vacancy identity."
                        )
                    seen.add(item.id)
                    try:
                        raw = self._request(f"/vacancies/{item.id}", {})
                    except _RemovedVacancy as exc:
                        result.warnings.append(str(exc))
                        continue
                    detail = _Detail.model_validate(raw)
                    if detail.id != item.id:
                        raise _ProviderError(
                            "HeadHunter returned an invalid vacancy identity."
                        )
                    result.jobs.append(
                        ProviderVacancy(
                            provider="headhunter",
                            native_id=detail.id,
                            title=detail.name,
                            company=detail.employer.name
                            if detail.employer
                            else item.employer.name
                            if item.employer
                            else "",
                            original_url=detail.alternate_url,
                            source_urls=[detail.alternate_url],
                            original_description=detail.description,
                            description_text=html_to_text(detail.description),
                            raw_payload=raw,
                            location=detail.area.name if detail.area else "",
                            skill_tags=[
                                tag.name.strip()
                                for tag in detail.key_skills
                                if tag.name and tag.name.strip()
                            ],
                            returned_dates={
                                key: raw[key]
                                for key in ("published_at", "created_at", "expires_at")
                                if key in raw
                            },
                            status="archived" if detail.archived else "active",
                            query_membership=[search_term.strip()],
                        )
                    )
                    if len(result.jobs) >= results_wanted:
                        return result
                page += 1
                if not data.items or page >= data.pages:
                    break
        except _ProviderError as exc:
            result.error = str(exc)
        except (ValidationError, ValueError, TypeError):
            result.error = "HeadHunter returned malformed vacancy data."
        return result
