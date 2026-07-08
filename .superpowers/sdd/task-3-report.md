Status: DONE_WITH_CONCERNS

Files changed:
- `backend/app/modules/individual_learning/cv_extractor.py`
- `backend/app/modules/individual_learning/models.py`
- `backend/app/modules/individual_learning/repository.py`
- `backend/app/modules/individual_learning/routes.py`
- `backend/app/modules/individual_learning/schemas.py`
- `backend/app/modules/individual_learning/service.py`
- `backend/tests/modules/individual_learning/test_cv_extractor.py`
- `backend/tests/modules/individual_learning/test_routes.py`

Behavior/API/schema changes:
- Added `extract_cv_text(filename, content_type, data) -> str` with PDF and DOCX support, reusing `handle_docx_bytes` for DOCX parsing and enforcing a minimum extracted-text length.
- Added `CVDocumentRead`, `CVSkillExtraction`, `CVExperienceExtraction`, and `CVProfileExtraction` schemas.
- Added `POST /individual-learning/cv` for authenticated individual users.
- Added repository persistence for uploaded `CVDocument` rows.
- Added service-layer CV upload flow that validates file presence, parses CV text, hashes content via `blob_service.sha256_hex()`, uploads bytes via `blob_service.upload_bytes()`, and stores the `CVDocument` row with `uploaded` status.

Tests/verification commands run:
- RED step documented but not executed locally: Docker execution was explicitly waived by the user, and host Python is 3.9.6 while backend runtime targets Python 3.12.
- `git diff --check` -> PASS
- manual file inspection of edited backend/test files -> PASS
- line-length static scan across edited files -> PASS
- Docker-based pytest/ruff commands -> NOT RUN (user explicitly waived Docker for this task)

TDD evidence:
- Wrote `backend/tests/modules/individual_learning/test_cv_extractor.py` before implementing `cv_extractor.py`.
- Expanded `backend/tests/modules/individual_learning/test_routes.py` with CV upload route coverage before implementing the route/service/repository path.
- RED/GREEN execution could not be performed locally because Docker was waived and host Python/runtime mismatch makes backend pytest non-authoritative here.

Commit hash(es):
- `aadc1b0` - `feat: add individual CV upload and parsing`

Self-review notes and concerns:
- Main concern: no runtime backend execution was performed locally, so this change is statically reviewed but not runtime-verified in this environment.
- The upload flow validates extracted CV text before persisting, but it does not yet persist extracted text or create downstream extraction-run records; that remains aligned with the task scope and later tasks.

---

Fix implemented:
- Wrapped `pypdf` parser failures in `backend/app/modules/individual_learning/cv_extractor.py` so malformed supported PDFs now raise `ValueError("Invalid PDF CV file")` instead of leaking parser exceptions through the service layer.
- Added regression coverage in `backend/tests/modules/individual_learning/test_cv_extractor.py` for malformed PDF bytes and `page.extract_text()` failures, while keeping the existing tests.
- Repaired the existing `_docx_bytes()` helper string assembly in the same test file so the preserved tests remain syntactically valid.

Files changed:
- `backend/app/modules/individual_learning/cv_extractor.py`
- `backend/tests/modules/individual_learning/test_cv_extractor.py`

Verification commands run/results:
- `python3 -m pytest backend/tests/modules/individual_learning/test_cv_extractor.py` -> NOT AUTHORITATIVE / FAILED DURING IMPORT because host Python is 3.9.6 and project backend imports Python 3.10+ / 3.11+ features (`datetime.UTC`).
- `PYTHONPATH=/Users/khajievroma/Projects/lab_tutor/.worktrees/individual-learning-full-loop/backend python3 -m pytest --noconftest backend/tests/modules/individual_learning/test_cv_extractor.py` -> NOT AUTHORITATIVE / FAILED DURING IMPORT because host Python is 3.9.6 and cannot evaluate project `str | None` annotations through imported modules.
- `PYTHONPATH=/Users/khajievroma/Projects/lab_tutor/.worktrees/individual-learning-full-loop/backend python3 - <<'PY' ... PY` (stubbed `app.modules.courses.file_processing`, exercised malformed PDF bytes and forced `extract_text()` failure) -> PASS; both cases raised `ValueError("Invalid PDF CV file")`.
- `PYTHONPATH=/Users/khajievroma/Projects/lab_tutor/.worktrees/individual-learning-full-loop/backend python3 - <<'PY' ... PY` (stubbed `handle_docx_bytes`, exercised unsupported type and too-short DOCX text) -> PASS; existing validation messages remained unchanged.
- `git diff --check` -> PASS

Commit hash:
- `5caca9b7b3b00fb8821f78eb77e90d1769b2d2a6`

Remaining concerns:
- Full backend pytest coverage was not runnable in this environment because Docker was explicitly waived and the available host Python is 3.9.6, below the backend’s target runtime.
