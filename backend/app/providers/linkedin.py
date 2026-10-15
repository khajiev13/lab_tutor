"""JobSpy LinkedIn adapter supporting countries outside Indeed's country enum."""

import pandas as pd
from bs4 import Tag
from jobspy.linkedin import LinkedIn
from jobspy.model import DescriptionFormat, Location, ScraperInput, Site


class LinkedInScraper(LinkedIn):
    def _get_job_details(self, job_id: str) -> dict:
        details = super()._get_job_details(job_id)
        # Some postings omit this optional field; JobSpy lowercases it later.
        details["job_level"] = details.get("job_level") or ""
        return details

    def _get_location(self, metadata_card: Tag | None) -> Location:
        tag = (
            metadata_card.find("span", class_="job-search-card__location")
            if metadata_card
            else None
        )
        raw_location = tag.get_text(strip=True) if tag else ""
        try:
            location = super()._get_location(metadata_card)
        except ValueError:
            # JobSpy uses its Indeed country enum for LinkedIn locations. LinkedIn
            # also serves countries (e.g. Uzbekistan) absent from that enum.
            parts = raw_location.rsplit(", ", 2)
            if len(parts) != 3:
                raise
            return Location(city=parts[0], state=parts[1], country=parts[2])
        if raw_location and not location.display_location():
            return Location(country=raw_location)
        return location


def scrape_linkedin_jobs(
    *, search_term: str, location: str, results_wanted: int, hours_old: int
) -> pd.DataFrame:
    """Keep JobSpy's search/detail parsing and all returned posting fields."""
    response = LinkedInScraper().scrape(
        ScraperInput(
            site_type=[Site.LINKEDIN],
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            linkedin_fetch_description=True,
            description_format=DescriptionFormat.MARKDOWN,
            distance=50,
        )
    )
    records = []
    for job in response.jobs:
        record = job.model_dump(mode="json")
        record["site"] = "linkedin"
        record["location"] = job.location.display_location() if job.location else ""
        records.append(record)
    return pd.DataFrame(records)
