from dataclasses import dataclass


@dataclass(frozen=True)
class JobSearchCountry:
    label: str
    jobspy_country: str
    location: str


DEFAULT_JOB_SEARCH_COUNTRY = "USA"

SUPPORTED_JOB_SEARCH_COUNTRIES: dict[str, JobSearchCountry] = {
    "USA": JobSearchCountry(
        label="United States",
        jobspy_country="USA",
        location="United States",
    ),
    "China": JobSearchCountry(
        label="China",
        jobspy_country="China",
        location="China",
    ),
    "UK": JobSearchCountry(
        label="United Kingdom",
        jobspy_country="UK",
        location="United Kingdom",
    ),
    "Canada": JobSearchCountry(
        label="Canada",
        jobspy_country="Canada",
        location="Canada",
    ),
    "Australia": JobSearchCountry(
        label="Australia",
        jobspy_country="Australia",
        location="Australia",
    ),
    "Singapore": JobSearchCountry(
        label="Singapore",
        jobspy_country="Singapore",
        location="Singapore",
    ),
}

COUNTRY_ALIASES: dict[str, str] = {
    "": DEFAULT_JOB_SEARCH_COUNTRY,
    "us": "USA",
    "u.s.": "USA",
    "u.s.a.": "USA",
    "usa": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "china": "China",
    "prc": "China",
    "uk": "UK",
    "u.k.": "UK",
    "united kingdom": "UK",
    "great britain": "UK",
    "canada": "Canada",
    "australia": "Australia",
    "singapore": "Singapore",
}


def normalize_job_search_country(raw_country: str | None) -> JobSearchCountry:
    normalized = (raw_country or "").strip().casefold()
    canonical = COUNTRY_ALIASES.get(normalized)
    if canonical is None:
        supported = ", ".join(
            country.label for country in SUPPORTED_JOB_SEARCH_COUNTRIES.values()
        )
        raise ValueError(
            f"Unsupported job search country: {raw_country!r}. "
            f"Supported countries: {supported}"
        )
    return SUPPORTED_JOB_SEARCH_COUNTRIES[canonical]
