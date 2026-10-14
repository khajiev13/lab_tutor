"""Explicit selected-provider collection; each branch returns its own evidence."""

import hashlib
import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import BoundedSemaphore
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.settings import settings
from app.providers.headhunter import HeadHunterService

from .countries import JobSearchCountry
from .schemas import (
    FetchJobsResult,
    JobSource,
    JobSourceOption,
    ProviderVacancy,
    SourceOutcome,
    safe_provider_payload,
)

SOURCES: tuple[JobSource, ...] = ("indeed", "linkedin", "headhunter")


def normalize_job_sources(raw: Sequence[str] | None) -> tuple[JobSource, ...]:
    if raw is None:
        return SOURCES
    if not raw or set(raw) - set(SOURCES):
        raise ValueError("Select at least one supported job provider")
    return tuple(source for source in SOURCES if source in raw)


def vacancy_identity(record: ProviderVacancy) -> str:
    if record.native_id:
        return f"id:{record.native_id}"
    if record.original_url:
        parsed = urlsplit(record.original_url)
        host = (parsed.hostname or "").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        if port is not None and port != {"http": 80, "https": 443}.get(parsed.scheme):
            host = f"{host}:{port}"
        canonical = urlunsplit(
            (parsed.scheme.lower(), host, parsed.path, parsed.query, parsed.fragment)
        )
        return f"url:{canonical}"
    raise ValueError("A provider-native ID or original posting URL is required")


def vacancy_content_hash(record: ProviderVacancy) -> str:
    content = {
        "payload": safe_provider_payload(record.raw_payload),
        "original_description": record.original_description,
        "title": record.title,
        "company": record.company,
        "original_url": record.original_url,
        "status": record.status,
        "skill_tags": record.skill_tags,
        "returned_dates": record.returned_dates,
    }
    return hashlib.sha256(
        json.dumps(
            content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class JobSourceService:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        access_token: str | None = None,
        jobspy_scraper: Callable | None = None,
        headhunter: HeadHunterService | None = None,
    ):
        self._user_agent = (user_agent or "").strip()
        self._access_token = (access_token or "").strip()
        self._scraper = jobspy_scraper
        self._headhunter = headhunter
        self._hh_slots = BoundedSemaphore(2)

    def catalog(self, country: JobSearchCountry) -> list[JobSourceOption]:
        options = []
        for source, label in [
            ("indeed", "Indeed"),
            ("linkedin", "LinkedIn"),
            ("headhunter", "HeadHunter"),
        ]:
            availability = "available"
            reason = None
            if (source == "indeed" and country.jobspy_country is None) or (
                source == "headhunter" and country.key != "Uzbekistan"
            ):
                availability = "unsupported_country"
                reason = "This provider does not support the selected country."
            elif source == "headhunter" and not (
                self._user_agent and self._access_token
            ):
                availability = "not_configured"
                reason = "HeadHunter application access is not configured."
            options.append(
                JobSourceOption(
                    id=source, label=label, availability=availability, reason=reason
                )
            )
        return options

    def validate_compatibility(
        self,
        country: JobSearchCountry,
        sources: tuple[JobSource, ...],
        *,
        evidence_sources: Sequence[str] = ("jobs",),
    ) -> None:
        if "jobs" not in evidence_sources:
            return
        normalized = normalize_job_sources(sources)
        options = {item.id: item for item in self.catalog(country)}
        if not any(
            options[source].availability == "available" for source in normalized
        ):
            raise ValueError(
                "No available job provider for this market. Configure provider access or choose another country."
            )

    def _collect(
        self,
        term: str,
        source: JobSource,
        country: JobSearchCountry,
        cap: int,
        hours_old: int,
    ) -> tuple[list[ProviderVacancy], list[str], bool]:
        try:
            if source == "headhunter":
                with self._hh_slots:
                    if self._headhunter is not None:
                        result = self._headhunter.search_jobs(
                            term, area_id="97", results_wanted=cap, hours_old=hours_old
                        )
                    else:
                        with httpx.Client() as client:
                            result = HeadHunterService(
                                client=client,
                                user_agent=self._user_agent,
                                access_token=self._access_token,
                            ).search_jobs(
                                term,
                                area_id="97",
                                results_wanted=cap,
                                hours_old=hours_old,
                            )
                warnings = list(result.warnings)
                if result.error:
                    warnings.append(result.error)
                return result.jobs, warnings, bool(result.error)
            scraper = self._scraper
            if scraper is None:
                from jobspy import scrape_jobs

                scraper = scrape_jobs
            kwargs = {
                "site_name": [source],
                "search_term": term,
                "location": country.location,
                "results_wanted": cap,
                "hours_old": hours_old,
                "description_format": "markdown",
                "linkedin_fetch_description": source == "linkedin",
                "verbose": 0,
            }
            if country.jobspy_country is not None:
                kwargs["country_indeed"] = country.jobspy_country
            frame = scraper(**kwargs)
            records = []
            warnings = []
            for row in frame.to_dict(orient="records"):
                raw = safe_provider_payload(row, self._access_token)

                def text_value(key, raw=raw):
                    value = raw.get(key)
                    return "" if value is None else str(value)

                try:
                    description = text_value("description")
                    record = ProviderVacancy(
                        provider=source,
                        native_id=text_value("id") or None,
                        title=text_value("title"),
                        company=text_value("company_name") or text_value("company"),
                        original_url=text_value("job_url"),
                        source_urls=list(
                            dict.fromkeys(
                                text_value(key)
                                for key in ("job_url", "job_url_direct")
                                if text_value(key)
                            )
                        ),
                        original_description=description,
                        description_text=description,
                        raw_payload=raw,
                        location=text_value("location"),
                        query_membership=[term],
                        returned_dates={
                            key: raw[key]
                            for key in ("date_posted", "date_expires")
                            if key in raw
                        },
                    )
                    vacancy_identity(record)
                    records.append(record)
                except ValueError:
                    warnings.append(
                        "A provider record lacked a valid posting identity or URL."
                    )
            return records, warnings, bool(warnings)
        except Exception:
            # Exceptions may embed authorization, request objects or vendor HTML.
            return (
                [],
                ["The selected job provider could not complete this query."],
                True,
            )

    def fetch(
        self,
        *,
        search_terms: Sequence[str],
        country: JobSearchCountry,
        sources: tuple[JobSource, ...],
        results_per_source: int = 15,
        hours_old: int = 72,
        evidence_sources: Sequence[str] = ("jobs",),
    ) -> FetchJobsResult:
        if "jobs" not in evidence_sources:
            return FetchJobsResult()
        if (
            not isinstance(results_per_source, int)
            or isinstance(results_per_source, bool)
            or not 1 <= results_per_source <= 100
            or hours_old <= 0
        ):
            raise ValueError(
                "Result cap must be from 1 to 100 with a positive time range"
            )
        terms = list(
            dict.fromkeys(
                term.strip()
                for term in search_terms
                if isinstance(term, str) and term.strip()
            )
        )
        if not terms:
            raise ValueError("At least one nonblank search query is required")
        selected = normalize_job_sources(sources)
        self.validate_compatibility(country, selected)
        options = {item.id: item for item in self.catalog(country)}
        available = tuple(
            source for source in selected if options[source].availability == "available"
        )
        # Initial workers include every available selected provider for many queries.
        tasks = [(source, term) for term in terms for source in available]
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
            futures = [
                pool.submit(
                    self._collect, term, source, country, results_per_source, hours_old
                )
                for source, term in tasks
            ]
            branches = [future.result() for future in futures]
        result = FetchJobsResult()
        seen = {}
        for source in selected:
            if options[source].availability != "available":
                result.outcomes[source] = SourceOutcome(
                    status="error",
                    warnings=[
                        f"{options[source].label} unavailable: {options[source].reason}"
                    ],
                )
                continue
            warnings = []
            failed = False
            provider_records = []
            for (branch_source, _term), (
                records,
                branch_warnings,
                branch_failed,
            ) in zip(tasks, branches, strict=True):
                if branch_source != source:
                    continue
                warnings.extend(branch_warnings)
                failed = failed or branch_failed
                for record in records:
                    # Never merge by title/company. Source snapshots stay separate.
                    key = (
                        source,
                        vacancy_identity(record),
                        vacancy_content_hash(record),
                    )
                    if key in seen:
                        repeated = seen[key]
                        repeated.query_membership = list(
                            dict.fromkeys(
                                [*repeated.query_membership, *record.query_membership]
                            )
                        )
                        repeated.source_urls = list(
                            dict.fromkeys([*repeated.source_urls, *record.source_urls])
                        )
                        continue
                    seen[key] = record
                    record.demand_identity = (
                        record.demand_identity or f"{source}:{key[1]}"
                    )
                    provider_records.append(record)
                    result.records.append(record)
            usable = [
                record
                for record in provider_records
                if len(record.description_text.strip()) >= 50
                and record.status != "archived"
            ]
            status = (
                "partial"
                if provider_records and (failed or warnings)
                else "error"
                if failed
                else "success"
                if usable
                else "empty"
            )
            result.outcomes[source] = SourceOutcome(
                status=status,
                received_count=len(provider_records),
                usable_count=len(usable),
                warnings=list(dict.fromkeys(warnings)),
            )
            for record in usable:
                result.jobs.append(
                    {
                        "title": record.title,
                        "company": record.company,
                        "description": record.description_text,
                        "description_text": record.description_text,
                        "url": record.original_url,
                        "site": source,
                        "native_id": record.native_id,
                        "skill_tags": record.skill_tags,
                        "source_urls": record.source_urls,
                        "search_term": record.query_membership[0]
                        if record.query_membership
                        else "",
                        "country": country.key,
                        "location": record.location,
                        "demand_identity": record.demand_identity,
                    }
                )
        return result


@lru_cache
def get_job_source_service() -> JobSourceService:
    return JobSourceService(
        user_agent=settings.hh_user_agent,
        access_token=settings.hh_access_token.get_secret_value()
        if settings.hh_access_token
        else None,
    )
