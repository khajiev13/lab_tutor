from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReleaseVersion = Annotated[str, Field(pattern=r"^\d+\.\d+$", max_length=20)]
SocCode = Annotated[str, Field(pattern=r"^\d{2}-\d{4}\.\d{2}$")]


class ReleaseInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: str
    active: bool
    attribution: str


class ReleaseList(BaseModel):
    items: list[ReleaseInfo]


class OccupationChoice(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    soc_code: SocCode
    title: str
    description: str


class OccupationSearch(BaseModel):
    release: str
    total: int
    items: list[OccupationChoice]


class Metric(BaseModel):
    scale_id: Literal["IM", "LV"]
    value: float | None
    minimum: float
    maximum: float
    status: Literal["reported", "missing", "suppressed", "not_relevant"]
    date: str | None
    quality: dict[str, Any]


class OnetEvidence(BaseModel):
    id: UUID
    release: str
    soc_code: SocCode
    occupation_title: str
    family: Literal["essential", "transferable", "software"]
    element_id: str
    label: str
    definition: str
    workplace_example: str | None
    ratings: dict[str, Metric]
    flags: dict[str, bool | None]
    source_url: str
    attribution: str


class OccupationSkills(BaseModel):
    release: str
    soc_code: SocCode
    items: list[OnetEvidence]


class OccupationSelection(BaseModel):
    run_id: UUID
    expected_candidate_revision: int = Field(ge=0)
    release: ReleaseVersion
    soc_codes: list[SocCode] = Field(min_length=1, max_length=5)

    @field_validator("soc_codes")
    @classmethod
    def unique_codes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Choose distinct occupations")
        return value
