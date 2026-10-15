"""Group role labels without collapsing or rewriting the original job evidence."""

import re
import unicodedata

_LEVEL = (
    r"(?:senior|sr\.?|junior|jr\.?|middle|mid|lead|principal|staff|"
    r"entry[- ]level|mid[- ]level|младший|старший|ведущий)\+?"
)
_PREFIX = re.compile(rf"^(?:{_LEVEL}\s+)+", re.IGNORECASE)
_SUFFIX = re.compile(rf"\s*(?:\(\s*{_LEVEL}\s*\)|[-,/]\s*{_LEVEL})$", re.IGNORECASE)
_ROLE_ALIASES = {
    "data engineer": "Data Engineer",
    "инженер данных": "Data Engineer",
    "data analyst": "Data Analyst",
    "аналитик данных": "Data Analyst",
}


def _without_level(title: str) -> str:
    title = _PREFIX.sub("", title.strip())
    return _SUFFIX.sub("", title).strip()


def _role_title(title: str) -> str:
    title = _without_level(" ".join(unicodedata.normalize("NFKC", title).split()))
    role = _ROLE_ALIASES.get(title.casefold())
    if role:
        return role
    # Collapse bilingual labels only when both halves name the SAME known role.
    # Mixed roles such as Data Scientist / ML Engineer remain separate groups.
    parts = [p.strip() for p in re.split(r"/|[()]", title) if p.strip()]
    roles = [_ROLE_ALIASES.get(_without_level(p).casefold()) for p in parts]
    if len(roles) > 1 and roles[0] and all(role == roles[0] for role in roles):
        return roles[0]
    return title.title() or "Other"


def group_jobs_by_title(jobs: list[dict]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for index, job in enumerate(jobs):
        groups.setdefault(_role_title(str(job.get("title") or "Other")), []).append(
            index
        )
    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])))
