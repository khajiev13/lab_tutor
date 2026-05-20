# Changelog

All notable changes to Lab Tutor are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-05-21 — Top Difficult Skills: attempted-only filtering

### Fixed

- **Class Overview "Top Difficult Skills" chart**: previously surfaced
  selected-but-never-attempted skills as "100% difficult / 0% mastery" because
  `avg_mastery` was averaged with a `0.0` fill for unattempted students,
  producing eight identical full-red bars regardless of real engagement. The
  chart now ranks only skills with a real practice signal (a `MASTERED` edge
  with a recorded mastery value) and surfaces unstarted skills in a "N more
  skills selected by students but not yet practiced" footnote.
- The same `attempted_count > 0` guard is now applied to the "highest
  perceived difficulty" insight and the `hardestSkill` summary on Class
  Overview, so unstarted skills no longer drive teacher recommendations.

### Backend

- ``GET_SKILL_DIFFICULTY`` Cypher: emits a new ``attempted_count`` column,
  derives ``perceived_difficulty`` only from students who attempted the skill
  (``1.0 - attempted_avg_mastery``), and orders unattempted skills last so
  truly-struggled skills always appear at the top.
- ``SkillDifficultyItem`` schema: added ``attempted_count: int = 0`` (default
  preserves backward compatibility with existing test fixtures).
- ``_build_automatic_skill_summaries`` now propagates ``attempted_count`` so
  the LLM planner can also distinguish "selected" from "actually struggled"
  when crafting What-If recommendations.

### Tests

- New repository test pins the Cypher to require ``attempted_count`` and the
  attempted-first ORDER BY, guarding against silent regressions.
- New service test: an unattempted skill must keep ``perceived_difficulty=0``
  end-to-end (not the legacy 1.0 default).
- New frontend tests in ``pages.test.tsx`` cover (a) filtering unattempted
  skills out of the chart with a deferred-skills footnote, and (b) the
  empty-state branch when no skill has been attempted yet.

---

## [Unreleased] — 2026-05-20 — ICCSE2026 ARCD Integration

This entry consolidates the LAB-side integration of the ICCSE2026 ARCD paper
(Khajiev et al., "ARCD: Attentive Relational Cognitive Diagnosis with V/R-aware
GCN over Multi-Relational Knowledge Graphs"). It pulls in the architectural fix,
hyperparameter corrections, supporting scripts, and the canonical paper-side
metrics that production agents reference at inference time.

### Imported paper results (canonical, do not reproduce locally)

The numbers below are imported verbatim from the ARCD_AGENT companion repo and
mirrored to ``backend/checkpoints/iccse2026_paper_results.json``. LAB does not
re-run the full multi-seed campaign — paper checkpoints are ``d_model=128``
(~5–7M params) while LAB production is ``d=2048`` (~170M params, 423 skills,
5-stage V/R-aware), so the .pt files are intentionally not vendored.

- **Synthetic V/R-aware corpus** (3 seeds, gcnfix2): AUC **0.829 ± 0.006**
  (lifted +2.5 pp from 0.804 ± 0.007 pre-fix).
- **XES3G5M public benchmark** (3 seeds, gcnfix2): AUC **0.784 ± 0.002** (lifted
  +4.4 pp from 0.740 ± 0.006, cross-seed std tightened 3.5×). ARCD beats
  simpleKT (0.768), GKT-CD (0.771), Q-KT (0.759), RCD (0.714), and DisenGCD
  (0.714) on the same split.
- **Learning Fellow PCO calibration** (500-session DeepSeek-v3.2 LLM judge,
  paper v2 prompt): Cohen's κ **0.902** at thresholds ``phi=3, tau_m=0.50,
  theta_decay=0.60``.

### Changed

- **`backend/app/modules/arcd_agent/model/gat/multi_relational.py`** — replaced
  ``BatchNorm1d`` over nodes with per-node ``LayerNorm`` and added per-layer
  residual connections in both ``BipartiteGCNStack`` and ``HomoGCNStack`` (paper
  log entry [2026-05-16T19:35] over-smoothing diagnostic). The 5-stage
  architecture itself is unchanged; only normalisation / residual / activation
  ordering moved.
- **`backend/app/modules/arcd_agent/agents/orchestrator.py`** — fixed
  ``_build_review_node`` ``PCODetector`` ``tau_m`` from ``0.60`` to ``0.50`` to
  match the paper-aligned threshold and the κ=0.902 calibration. Other
  ``PCODetector`` instantiations (in ``cognitive_diagnosis/service.py`` and the
  default constructor) were already correct.
- **`backend/arcd_train.py`** — corrected default hyperparameters to the
  post-fix ICCSE2026 values (``focal_alpha=0.65`` was 0.25, ``mastery_weight=0.1``
  was 0.2, ``rdrop_alpha=0.1`` was 0.3, ``label_smoothing=0.05`` was 0.1).
  These defaults fixed the threshold-collapse anti-pattern observed in the
  ``roma_synth_v6_2048`` baseline (Recall 0.991, Specificity 0.031, MCC 0.082).
  Also added a new ``--resume <path>`` flag that warm-starts from an existing
  ``best_model.pt``: model state-dict is loaded, ``H_skill_raw`` is restored
  from the checkpoint when present, and ``--epochs`` then specifies how many
  *additional* epochs to train. Used during this integration to extend the
  smoke run from 5 → 8 epochs without retraining from scratch.

### Added

- **`backend/checkpoints/iccse2026_paper_results.json`** — canonical paper-side
  metrics manifest. Authoritative source for any "paper number" cited in
  CHANGELOG, docs, agent prompts, and regression tests. Numbers are imported
  from ``ARCD_AGENT/runs/iccse2026_screen/{synthetic,xes3g5m}/_summary.json``
  and ``ARCD_AGENT/runs/iccse2026_lf_llm_v2/lf_llm_judge_summary.json``.
- **`backend/scripts/iccse2026_synth_orchestrate.py`** + **`iccse2026_synth_retrain.sh`**
  — synth retrain orchestrator and runner. Mirrors the ARCD_AGENT screening
  campaign so LAB can produce a refactored-arch-compatible checkpoint without
  leaving the repo. ICCSE-corrected hyperparameters are baked into the shell
  defaults.
- **`backend/scripts/calibrate_pco_with_llm.py`** — LF-PCO calibration CLI
  ported from ``ARCD_AGENT/scripts/iccse2026_eval_lf_llm.py``. Runs the rule-
  based ``PCODetector`` and an LLM judge over a synthetic-cohort sweep, writes
  ``backend/runs/lf_llm_calibration_v2/lf_llm_judge_{summary,results}.json``.
  The local 5-session dry-run is committed as evidence the CLI works in this
  repo; the canonical κ=0.902 from the 500-session run remains the paper number.
- **`backend/scripts/writeback_arcd_embeddings.py`** — writes the 5 GAT stage
  outputs (``arcd_h_skill``, ``arcd_h_question``, ``arcd_h_video``,
  ``arcd_h_reading``, ``arcd_h_student``) back to Neo4j Aura at 2048-dim. Run
  after every successful ARCD retrain so the production agents can consume the
  contextual embeddings instead of falling back to ``name_embedding``. Supports
  ``--dry-run`` and ``--skills-only``.
- **`backend/tests/modules/arcd_agent/`** — regression suite locking the
  refactored architecture in place (LayerNorm not BatchNorm, all 5 stage
  outputs, paper-aligned PCO thresholds, ``arcd_train.py`` default HPs).
  11 tests, all green at integration time.
- **`THESIS4_BLUEPRINT.md`** — outline of the thesis / paper revision incorporating
  the ICCSE2026 results.

### Checkpoint migration notes (Option A — code-only ship)

- The legacy ``backend/checkpoints/roma_synth_v6_2048/best_model.pt`` was
  trained with the BatchNorm-era code path (``fwd_bns`` / ``bwd_bns`` / ``bns``
  state-dict keys) and is **not** state-dict-compatible with the LayerNorm
  refactor (``fwd_norms`` / ``bwd_norms`` / ``norms``).
  ``ModelRegistry.from_dir`` catches the ``RuntimeError`` and degrades to
  ``is_available=False``, at which point ARCD-derived mastery falls back to
  the existing heuristic path. **This integration keeps that behaviour**:
  ``DEFAULT_CHECKPOINT_DIR`` is left at ``roma_synth_v6_2048``. The graceful
  fallback was already in place, so end-user agents are unaffected; what
  changes is that the code path they execute is now the corrected one.
- A 5+3-epoch smoke retrain on ``roma_synth_v5_1k_200k`` was executed during
  this integration purely as a **state-dict shape validation** of the
  refactored architecture. Trajectory:

  | Epoch | AUC | Notes |
  |---|---|---|
  | 1–3 | 0.5031 → 0.5350 → 0.6407 | LR warmup, first fit |
  | 4–5 | 0.6410 → 0.6409 | plateau at LR 1e-3 |
  | 6–8 (resumed) | 0.6412 → **0.6417** → 0.6395 | LR re-warmup after `--resume` |

  Best val AUC = **0.6417** at epoch 7. The plateau is structural, not an
  early-stopping artefact: the production ``d=2048`` (~170M-param) model is
  ~33× larger than the paper's ``d_model=128`` (~5–7M) checkpoint, while the
  v5 synth corpus only provides ~32K training windows — far too few to lift
  a 170M-param model toward the paper's 0.829. The smoke checkpoint is
  therefore **NOT** promoted to the registry default and the trained
  weights are **NOT** written back to Neo4j (writing random-Gaussian-init
  skill embeddings into production graph would be incorrect). The
  canonical numbers cited in this CHANGELOG, in agent prompts, and in
  regression docs come exclusively from
  ``backend/checkpoints/iccse2026_paper_results.json``.
- A future paper-grade retrain that **does** populate the registry must (a)
  point ``--neo4j-*`` flags at the production graph so all 423 skills resolve
  through ``name_embedding``, (b) train on the production multi-tenant
  interaction corpus rather than the v5 synth slice, and (c) follow the
  retrain checklist in ``CLAUDE.md``. After such a run,
  ``backend/scripts/writeback_arcd_embeddings.py`` (shipped in this integration)
  is the supported way to push the 5 GAT stage outputs back to Neo4j.

---

## [Superseded by 2026-05-20] — 2026-05-17

### Verified

- **Post-fix GCN validation closed** — ICCSE2026 paper revision validated the
  bipartite-residual GCN refactor (mirrored to LAB on 2026-05-16) with three
  independent measurements:
  - **3-seed XES3G5M sweep (seeds 42/137/271, 20-ep)**: AUC lifted $+4.4$ pp
    ($0.740_{\pm.006} \rightarrow 0.784_{\pm.002}$, cross-seed std tightened
    $3.5\times$).
  - **3-seed synthetic sweep (V/R-aware, seeds 42/137/271)**: AUC lifted $+2.5$ pp
    ($0.804_{\pm.007} \rightarrow 0.829_{\pm.006}$).
  - **pyKT 5-fold ARCD-only re-run**: AUC $0.783_{\pm.007}$ ($n{=}5$) vs pre-fix
    $0.720_{\pm.058}$ — $+6.3$ pp lift, $8.2\times$ tighter variance. This is the
    cross-fold independent confirmation that the variance anomaly that motivated
    the GCN audit (April–May 2026) was a pure code bug (multi-stage over-smoothing
    in `BipartiteGCNStack` / `HomoGCNStack`), now closed.

### Added

- **Real-LLM Learning Fellow PCO judge** (paper-side calibration tool, sitting in
  `ARCD_AGENT/scripts/iccse2026_eval_lf_llm.py` for the ICCSE replication harness).
  500-session synthetic-cohort evaluation against the deployed `PCODetector`
  thresholds (`phi=3`, `tau_m=0.50`, `theta_decay=0.60` — same as the LAB
  production agent). Cohen's $\kappa = 0.902$ between the rule-based detector and
  deepseek-v3.2 as an external judge after a prompt-fix iteration (v1 prompt was
  underspecified on the streak / decay-risk thresholds and yielded $\kappa = 0.463$;
  v2 prompt with explicit `phi=3` and `decay_risk > 0.60` thresholds yielded
  $\kappa = 0.902$). The result confirms LAB's `PCODetector` precision ($0.956$,
  $N{=}500$) is calibrated against an independent LLM observer — useful as future
  inter-rater evidence for the production Learning Fellow agent.

### Documentation

- **`ICCSE2026_Paper/main.{pdf,tex}`** (ARCD_AGENT companion repo) — the
  submission-ready manuscript incorporates all post-fix validation
  results.  W4 verification re-review (`ICCSE2026_Paper/reviews/W4_rereview.md`)
  closes the W0 senior-review CRITICALs and elevates the weighted score from
  $51/100$ to $71/100$ (Accept band).
- Wiki log: `wiki/log.md` entries from `[2026-05-15]` to `[2026-05-17T02:15]`
  trace the per-turn revision history.

---

## [Unreleased] — 2026-05-16

### Verified

- **W1.7 parity confirmation (no code change required)** — ICCSE2026 paper integrity
  audit revealed that `ARCD_AGENT/scripts/retrain_arcd_v2.py` `KTDataset` had been
  training the synthetic dataset as question-only (V/R events from
  `watched_events.csv` + `read_events.csv` never reached gradient descent). A 3-seed
  V/R-aware re-run lifted ARCD synth AUC from $0.785_{\pm.018}$ to $0.804_{\pm.007}$
  (+1.9 pp, std halved).
- Investigation confirmed **LAB_ARCD_INTEGERATE is already V/R-aware end-to-end**:
  - `knowledge_graph_builder/synthgen/exporter.py` (~L600–L693) merges question +
    video + reading events into `train.parquet` / `test.parquet` with `event_type`
    (0/1/2) and `entity_idx` columns before saving.
  - `backend/arcd_train.py` `SynthgenSequenceDataset` (L478–L632) consumes
    `event_type` / `entity_idx` directly; the docstring explicitly notes
    "Video/reading events are kept in history for temporal attention" and the
    target must be a question event.
  - Multi-relational GAT (`backend/app/modules/arcd_agent/model/gat/multi_relational.py`)
    and temporal attention (`temporal_attention.py`) have the V/R branches and the
    3-event-type entity table that ARCD_AGENT's W1.7 fix relies on.
- Net effect: **no LAB source-code change required**. The W1.7 fix only re-aligns the
  ICCSE replication harness (`ARCD_AGENT`) with the production pipeline that LAB has
  already shipped.

---

## [Unreleased] — 2026-04-17

### Added

#### Backend

- **`backend/app/modules/cognitive_diagnosis/`** — New FastAPI module
  - `GET /diagnosis/arcd-twin/{course_id}` — ARCD twin snapshot for authenticated student
  - `GET /diagnosis/student-events/{course_id}` — List learning events
  - `POST /diagnosis/student-events/{course_id}` — Record a learning event
  - `POST /diagnosis/adaptive-exercise/{course_id}` — Generate adaptive exercise
  - `GET /diagnosis/interaction-stats/{course_id}` — Interaction summary
  - `POST /diagnosis/engagement-signal/{course_id}` — Log engagement signal
  - Pydantic v2 schemas: `StudentEventCreate`, `ExerciseRequest`, `PortfolioResponse`, …
  - Neo4j repository with `UPSERT_MASTERED`, `UPSERT_MASTERY_BATCH`, `CREATE_ATTEMPTED`,
    `UPSERT_ENGAGES_WITH_*`, `GET_STUDENT_TWIN`, `GET_SKILL_PREREQS`, `GET_SKILL_LIST`
  - Service layer: `CognitiveDiagnosisService`

- **`backend/app/modules/teacher_digital_twin/`** — New FastAPI module
  - `GET /teacher-twin/{course_id}/skill-difficulty`
  - `GET /teacher-twin/{course_id}/skill-popularity`
  - `GET /teacher-twin/{course_id}/class-mastery`
  - `GET /teacher-twin/{course_id}/student-groups`
  - `POST /teacher-twin/{course_id}/what-if`
  - `POST /teacher-twin/{course_id}/simulate-skill`
  - `POST /teacher-twin/{course_id}/simulate-skills`
  - `GET /teacher-twin/{course_id}/student/{student_id}/portfolio`
  - `GET /teacher-twin/{course_id}/student/{student_id}/twin`
  - Pydantic v2 schemas: `SkillDifficultyResponse`, `ClassMasteryResponse`,
    `WhatIfRequest/Response`, `MultiSkillSimulationRequest/Response`, …
  - Neo4j repository with 9 optimised read queries
  - Service layer: `TeacherDigitalTwinService` (K-means student clustering, what-if logic)

- **Neo4j Cypher refactor** — 9 queries across both repositories updated to follow
  project best practices:
  - Replaced nested `OPTIONAL MATCH` with list comprehensions (`[... | r.prop][0]`)
  - Replaced `WITH … COLLECT()` accumulations with `COLLECT {}` subqueries (Neo4j 5+)
  - `MERGE` for all upserts; `UNWIND` for batch writes

- **Backend tests** (`backend/tests/modules/`)
  - `cognitive_diagnosis/`: `test_schemas.py`, `test_repository.py`, `test_service.py`,
    `test_routes.py` — 60+ assertions
  - `teacher_digital_twin/`: `test_schemas.py`, `test_repository.py`, `test_service.py`,
    `test_routes.py` — 60+ assertions
  - All tests use `TestClient` + JWT fixtures + mocked Neo4j driver

#### Frontend

- **`src/features/arcd-agent/api/teacher-twin.ts`** — Typed `apiFetch` wrappers for
  all Teacher Digital Twin endpoints

- **New pages**
  - `TeacherTwinPage` — Teacher dashboard (skill difficulty, popularity, class mastery)
  - `ClassOverviewPage` — Class-wide mastery heatmap
  - `ClassRosterPage` — Paginated student list
  - `StudentDrilldownPage` — Per-student portfolio + twin viewer

- **Modified pages**
  - `StudentPage` — Updated for new `StudentPortfolio` type shape
  - `JourneyPage` — Updated for `timeline`/`summary` fields

- **New/updated components**
  - `chat-tab`, `pathgen-tab`, `journey-map-tab`, `twin-viewer-tab`, `schedule-tab`,
    `unified-tab` — Aligned to new `StudentPortfolio` type

- **New contexts**
  - `TeacherDataContext` — Teacher-side course/class data with polling
  - Updates to `TwinContext`, `DataContext` for new field shapes

- **Frontend tests** (`src/features/arcd-agent/`)
  - `api/teacher-twin.test.ts` — API wrapper tests
  - `context/context.test.tsx` — `TeacherDataContext`, `DataContext`, `TwinContext`
  - `pages/pages.test.tsx` — Smoke tests for all 6 pages
  - `components/tabs.test.tsx` — Smoke tests for all 6 tab components
  - `src/test/fetchMock.ts` — Lightweight `vi.stubGlobal` fetch helper

#### Documentation

- `docs/COGNITIVE_DIAGNOSIS_AND_TEACHER_TWIN.md` — Full module reference
  (endpoints, schemas, Neo4j graph schema, env vars, test commands)
- `README.md` — Updated Module Status table, API Routes table, Testing section,
  and Documentation table

### Changed

- `backend/main.py` — Registered `cognitive_diagnosis.router` and
  `teacher_digital_twin.router`
- `README.md` — Expanded Testing section with per-module test matrix
