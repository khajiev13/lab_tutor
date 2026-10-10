# O*NET catalog operations

The catalog uses seven official, versioned bulk CSV files. It needs no O*NET
API credential. PostgreSQL stores the release manifest, occupations, original
source rows and evidence. Teacher approval and graph publication are separate
steps in the market-demand flow.

## Validate a release

Run the administrative CLI in the backend container:

```bash
docker exec lab_tutor_backend /app/.venv/bin/python scripts/import_onet.py --release 31.0 --validate-only
```

To use files already available inside the container:

```bash
docker exec lab_tutor_backend /app/.venv/bin/python scripts/import_onet.py --release 31.0 --from-dir /tmp/onet-31.0-validation --validate-only
```

Validation parses every required file without initializing a database
connection. The JSON output reports source hashes and row counts, occupations,
evidence families, metric statuses and software flags. A failed validation
returns a nonzero exit code. Keep its error and the source files for diagnosis.

The required files are `occupation_data.csv`, `job_titles.csv`,
`content_model_reference.csv`, `essential_skills.csv`,
`transferable_skills.csv`, `software_skills.csv` and `scales_reference.csv`.
The default download cache is `/app/data/onet`, outside tracked source code.

The current importer validated the cached official 31.0 files in Docker on
10 October 2026. All seven source URLs, byte lengths and SHA256 values matched
the download manifest. This check made no SQL writes or activation changes.

| Parsed data | Count |
| --- | ---: |
| Occupations | 1,016 |
| Essential skill evidence | 9,100 |
| Transferable skill evidence | 22,750 |
| Software skill evidence | 31,821 |
| Reported metrics | 60,039 |
| Suppressed metrics | 157 |
| Not-relevant metrics | 3,504 |

These are occupation-linked records and per-scale metrics, not distinct
technology names or job-posting counts. They describe this pinned release;
future releases need their own validation instead of matching these totals.

## Import and activate

After integration acceptance, import into the database configured for the
target backend. Check that environment before running this command:

```bash
docker exec lab_tutor_backend /app/.venv/bin/python scripts/import_onet.py --release 31.0 --from-dir /tmp/onet-31.0-validation --activate
```

Omit `--activate` to import without changing the active catalog. Only complete
imports become ready. Import and activation use one transaction; a failure
leaves the previous active release intact. There is no scheduled update.

A manifest compares release, official source URLs and SHA256 hashes. Importing
identical content again is idempotent even if retrieval times differ. Changed
content under an existing version is rejected. Investigate that mismatch
instead of replacing historical evidence. Import a future official release
under its own version and retain releases referenced by saved analyses.

## Interpret evidence

Importance uses its original 1–5 scale; occupational level uses 0–7. Values are
specific to an occupation. Reported, missing, suppressed and not-relevant
metrics remain distinct, with original dates and quality metadata. Unavailable
ratings are not zero. Software examples retain Hot Technology and In Demand
flags and have no invented importance or level ratings.

Only an equivalent descriptor supplies a candidate's sortable O*NET rating.
Broader or related descriptors remain labelled context. The teacher chooses
the active occupation when sorting; ratings are not averaged across roles.
Ratings remain separate from observed job frequency and quiz-based mastery.

Each displayed association retains its pinned release, SOC, original
descriptor, source URL and attribution. Preserve the imported USDOL/ETA
attribution and CC BY 4.0 notice when displaying or exporting O*NET evidence.

## Publication and recovery

Teachers may shortlist O*NET references in a draft. Every skill newly approved
through the combined flow also needs a genuine supporting job posting with
its original URL. O*NET reference links do not satisfy that requirement.
Approval validates the current server-side review and evidence before saving
publication; graph projection has a separate completion status.

An unavailable catalog does not disable jobs-only analysis. An existing
analysis retains its pinned release. Clearing its chat does not remove
approved evidence, saved student learning paths, resources or quiz mastery.

During rollout, validate cached official files and complete the isolated
integration checks before activating the intended environment. The current
verification record is the HTML implementation report under
`output/headhunter-explorer/implementation-status.html`.
