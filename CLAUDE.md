# Lab Tutor — Claude Code Project Instructions

## Project Architecture
- **Monorepo Structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + Shadcn UI
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (Modular Onion Architecture)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: Graph view for integrated features (Users, Courses, Enrollments). Check neo4j MCP server for schema.
  - **PostgreSQL**: Relational data (Auth, Courses, Enrollments) via SQLAlchemy. Cloud instance + local for testing.

## Development Workflows

### Frontend (`/frontend`)
- Package Manager: `npm`
- Dev Server: `npm run dev`
- Build: `npm run build`
- Linting: `npm run lint` (ESLint Flat Config)
- Styling: TailwindCSS v4 with `cn()` utility
- Components: Shadcn UI in `@/components/ui`. Use `npx shadcn@latest add [component]`. Use shadcn MCP tool for up-to-date components.

### Backend (`/backend`)
- Package Manager: `uv` (Python 3.12+)
- Run Server: `uv run fastapi dev main.py`
- Testing: `LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v`
- Linting/Formatting: `uv run ruff check .` and `uv run ruff format .`
- Database Migrations: `Base.metadata.create_all(bind=engine)` in `lifespan` (no Alembic yet)
- Health Check: `GET /health`

### Knowledge Graph (`/knowledge_graph_builder`)
- Ingestion: `python scripts/ingest_ready_data.py`
- Dependencies: `uv add <dependency>` — do not hardcode

## Coding Conventions

### Frontend (React/TypeScript)
- Imports: `@/` alias for `src/`
- Forms: `react-hook-form` with `zod` resolvers
- State: `Context` for global state (e.g., `AuthContext`)
- API: `axios` instances from `@/services/api`
- TypeScript `strict: true` — handle `null`/`undefined` explicitly

### Backend (Python/FastAPI)
- Modular Onion Architecture. Group by feature in `modules/`
- Layers: Domain (`models.py`, `schemas.py`) → Repository (`repository.py`) → Service (`service.py`) → API (`routes.py`)
- Core & Providers: `core/` for shared components, `providers/` for infrastructure
- Type hints: Python 3.10+ syntax (`str | None`, `list[str]`)
- ORM: SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `DeclarativeBase`)
- Validation: Pydantic v2 (`ConfigDict(from_attributes=True)`)
- Dependency Injection: `Depends()` to inject Services into Routes, Repos into Services

## Integration Points
- CORS: Backend allows `localhost:5173`, `localhost:5174`, `localhost:3000`
- Auth: JWT-based. Frontend stores token; Backend validates via `OAuth2PasswordBearer`
- Docker: `docker-compose up -d` for Neo4j and Backend

## Git Workflow
- Always work on feature-scoped branches (never commit directly to `main`)
- Branch naming: `feat/<name>`, `fix/<name>`, `refactor/<area>`, `chore/<topic>`
- Small, coherent commits with descriptive messages
- PR descriptions must include scope, behavior changes, config, and verification steps

## Runtime Configuration (Backend)
- SQL: `LAB_TUTOR_DATABASE_URL` (required)
- Neo4j (optional): `LAB_TUTOR_NEO4J_URI`, `LAB_TUTOR_NEO4J_USERNAME`, `LAB_TUTOR_NEO4J_PASSWORD`, `LAB_TUTOR_NEO4J_DATABASE`
- Azure Blob (optional): `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING`, `LAB_TUTOR_AZURE_CONTAINER_NAME`

## Code Quality
- Less code is better code
- Don't over-engineer — solve the current problem
- No dead code — remove unused imports, variables, functions
- DRY — extract shared logic
- Single Responsibility
- Meaningful names
- Follow established patterns in the codebase
- Flat over nested — prefer early returns and guard clauses
- Every line must earn its place

## ARCD Model — Retraining Notes

### Current State (as of 2026-04-20)
| Artifact | Value | Source |
|---|---|---|
| Skills in Neo4j **now** | **423** | Verified live: 229 `:BOOK_SKILL` + 194 `:MARKET_SKILL` |
| Skills in active vocab | **229** | `vocab.json` concept keys — trained checkpoint is stale |
| ⚠ Skill count mismatch | **194 skills NOT in model** | Next training must use all 423 skills |
| Questions in graph | 1 999 | `vocab.json` question keys |
| Videos in graph | 354 | `vocab.json` video keys (roma_synth_v1_reg) |
| Readings in graph | 364 | `vocab.json` reading keys (roma_synth_v1_reg) |
| `H_skill_raw` shape | (229, 48) | Stale — next training: (423, 2048) |
| Active checkpoint | `backend/checkpoints/roma_synth_v1_reg/` | Stale — must retrain |

### ✅ RULE: ALL embedding dimensions must equal 2048 (the KG native dimension)

The knowledge graph stores all node embeddings at **2048 dimensions** (LLM text-embedding at KG build time).
Every ARCD model embedding — both inputs and outputs of all 5 GAT stages — **must also be 2048**.
This is the canonical embedding size for this project. Never use 48, 96, or any other size.

#### Current state (broken — dimensions are mismatched)
| Checkpoint `roma_synth_v1_reg` | Current dim | Required dim |
|---|---|---|
| `H_skill_raw` input to Stage 1 | **48** (random Xavier) | **2048** (from `name_embedding`) |
| `h_s`  Stage 1 output — skills | **96** | **2048** |
| `h_qa` Stage 2 output — questions | **96** | **2048** |
| `h_v`  Stage 3 output — videos | **96** | **2048** |
| `h_r`  Stage 4 output — readings | **96** | **2048** |
| `h_u`  Stage 5 output — students | **96** | **2048** |

#### What exists in Neo4j today (verified 2026-04-20)
| Node type | Property | Dim | Coverage |
|---|---|---|---|
| `:SKILL` / `:BOOK_SKILL` / `:MARKET_SKILL` | `name_embedding` | **2048** | 423 / 423 |
| `:SKILL` / `:BOOK_SKILL` | `h_skill` (KG builder output, not ARCD) | **2048** | 262 / 423 |
| `:CONCEPT` | `embedding` | **2048** | 814 / 1466 |
| `:QUESTION` | *(no embedding property yet)* | — | 0 |
| `:VIDEO_RESOURCE` | *(no embedding property yet)* | — | 0 |
| `:READING_RESOURCE` | *(no embedding property yet)* | — | 0 |
| `:USER` / `:STUDENT` | *(no embedding property yet)* | — | 0 |

### ⚠ Must Re-train When…
1. **Skill count changes** — adding/removing `:SKILL`, `:BOOK_SKILL`, or `:MARKET_SKILL` nodes in Neo4j changes `len(vocab["concept"])`, which changes `H_skill_raw` shape and invalidates the GAT weights.
2. **New resource interactions added to synthgen** — `roma_synth_v1_reg` is the first checkpoint with videos and readings; any earlier checkpoint is missing those signals.
3. **`H_skill_raw` persistence fix** — currently `H_skill_raw` is Xavier-initialized fresh at both train and inference time and **not saved** in `state_dict`. Fix `arcd_train.py` to save it and `model_registry.py` to restore it.

### ⚠ Required changes before next training run

#### 1. Set both `--d-skill` and `--d` to 2048 in training command
**These are now the defaults in `arcd_train.py` — no explicit flags needed.**
```bash
cd backend
# d_skill_embed=2048, d=2048 are the new defaults — just point to the new data dir
uv run python arcd_train.py \
    --data-dir ../knowledge_graph_builder/data/synthgen/<new_run_id> \
    --out-dir checkpoints/<new_run_id>
```

#### 2. Initialize `H_skill_raw` from `name_embedding` in Neo4j (not random Xavier)
In `arcd_train.py` / `model_registry.py`, replace the Xavier random init:
```python
# BEFORE (wrong):
H = torch.empty(n_skills, d_skill_embed)
nn.init.xavier_uniform_(H)

# AFTER (correct): load name_embedding from Neo4j for each skill in vocab order
H = torch.zeros(n_skills, 2048)
for skill_name, idx in vocab["concept"].items():
    row = neo4j_session.run(
        "MATCH (s) WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL) "
        "AND s.name = $name RETURN s.name_embedding AS emb",
        name=skill_name
    ).single()
    if row and row["emb"]:
        H[idx] = torch.tensor(row["emb"], dtype=torch.float32)
H_skill_raw = H.to(device)  # shape (229, 2048) — saved in checkpoint state_dict
```

#### 3. After training, write all 5 GAT stage outputs back to Neo4j
Each stage output is the learned 2048-dim contextual embedding for that entity type.
Write as a **new property** — do NOT overwrite `name_embedding` or `h_skill`.

| GAT Stage | Output tensor | Neo4j node type | New property to write |
|---|---|---|---|
| Stage 1 — Skills | `h_s  (229, 2048)` | `:SKILL` `:BOOK_SKILL` `:MARKET_SKILL` | `arcd_h_skill` |
| Stage 2 — Questions | `h_qa (1999, 2048)` | `:QUESTION` | `arcd_h_question` |
| Stage 3 — Videos | `h_v  (354, 2048)` | `:VIDEO_RESOURCE` | `arcd_h_video` |
| Stage 4 — Readings | `h_r  (364, 2048)` | `:READING_RESOURCE` | `arcd_h_reading` |
| Stage 5 — Students | `h_u  (4000, 2048)` | `:USER` `:STUDENT` | `arcd_h_student` |

```python
# Pseudo-code — run once after training completes
# Skills
for skill_name, idx in vocab["concept"].items():
    session.run(
        "MATCH (s) WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL) AND s.name=$n "
        "SET s.arcd_h_skill = $v",
        n=skill_name, v=h_s[idx].tolist()
    )
# Questions
for q_name, idx in vocab["question"].items():
    session.run("MATCH (q:QUESTION {id:$n}) SET q.arcd_h_question=$v", n=q_name, v=h_qa[idx].tolist())
# Videos
for v_name, idx in vocab["video"].items():
    session.run("MATCH (v:VIDEO_RESOURCE) WHERE coalesce(v.id,v.url)=$n SET v.arcd_h_video=$val",
                n=v_name, val=h_v[idx].tolist())
# Readings
for r_name, idx in vocab["reading"].items():
    session.run("MATCH (r:READING_RESOURCE) WHERE coalesce(r.id,r.url)=$n SET r.arcd_h_reading=$val",
                n=r_name, val=h_r[idx].tolist())
# Students (only real/non-synthetic students — filter by user vocab)
for u_name, idx in vocab["user"].items():
    session.run("MATCH (u:USER {id:toInteger($n)}) SET u.arcd_h_student=$v",
                n=u_name, v=h_u[idx].tolist())
```

### v4 Retrain — Mastery + UNK-Student Fix (2026-04-20)

The v3 (`roma_synth_v3_2048`) checkpoint had two latent bugs that collapsed
`MasteryHead` to ~zero outputs at inference:

| # | Bug | Fix (v4) |
|---|---|---|
| 1 | `MasteryLoss` computed unmasked MSE over `(B, n_skills)` even though `mastery_target` is ~95% zeros (only observed skills are filled). The model learned to predict zero everywhere to minimize the loss. | `MasteryLoss` now accepts a `mask` and computes MSE **only over observed skills**. `mastery_weight` raised from `0.05 → 0.5`. |
| 2 | OOV / unseen students fell back to `student_id=0` at inference (in `predict_mastery` / `predict_correctness`). That index is also a real synthetic student, so the v3 cold-start dropout (which **zeroed** `e_u`) never trained a generic prior — it just contaminated student 0. | A reserved `<UNK_STUDENT>` slot is appended at index `n_real_students` (so `n_students = n_real_students + 1`). Cold-start dropout swaps the student id for the UNK index instead of zeroing `e_u`. `model_registry.py` and both notebooks now route OOV students to this UNK slot. |

#### v4 retrain command

```bash
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python arcd_train.py \
    --data-dir ../knowledge_graph_builder/data/synthgen/<new_run_id> \
    --out-dir   checkpoints/roma_synth_v4_2048'
```

Defaults that changed in v4 (no flag needed unless overriding):
- `--mastery-weight 0.5` (was `0.2`, originally `0.05`)
- `--student-emb-dropout 0.3` (was `0.0`)

### v6 Hyperparameter Fixes — AUC Improvement (2026-04-21)

**Root cause of v5 val_loss oscillation / slow AUC convergence:**
1. `focal-alpha=0.75` was wrong — synthgen has ~79% correct responses, so the **positive class must be down-weighted** (use `0.25`), not up-weighted.
2. `mastery-weight=0.5` was too high — mastery targets cover only ~5% of skills per student, making the gradient sparse and noisy; reduced to `0.2`.
3. `warmup-epochs=5` was too long — 5 unstable warm-up epochs wasted early training.
4. `dropout=0.1` too mild for 170M parameters on ~32K training windows.

#### v6 retrain command

```bash
cd backend
uv run python arcd_train.py \
  --data-dir ../knowledge_graph_builder/data/synthgen/<run_id> \
  --out-dir checkpoints/roma_synth_v6_2048
# All improved defaults apply automatically — no extra flags needed
```

Defaults changed in v6:
- `--focal-alpha 0.25` (was `0.75` — critical fix)
- `--mastery-weight 0.2` (was `0.5`)
- `--warmup-epochs 2` (was `5`)
- `--dropout 0.2` (was `0.1`)
- `--weight-decay 5e-4` (was `1e-4`)
- `--student-emb-dropout 0.3` (unchanged)

After training:
1. `model_registry.get_registry()` already points to `roma_synth_v4_2048` — no edit needed unless using a custom run id.
2. Re-run `backend/notebooks/arcd_inference_walkthrough.ipynb` and confirm:
   - `mastery_before` has non-trivial mean (≥ 0.3, ideally close to global synthgen mean).
   - `decay_us` has real spread for practiced skills.
   - OOV student print line shows `OOV → UNK slot (idx=N)` instead of falling back to `0`.

### Re-train Checklist
```
1. Verify all 423 skills in Neo4j have name_embedding populated (run KG builder if not)
2. Re-run synthgen with ALL 423 skills:
   cd knowledge_graph_builder && uv run python -m synthgen --run-id <new_id>
   (synthgen fetch_skills already queries SKILL + BOOK_SKILL + MARKET_SKILL)
3. Fix H_skill_raw init: load name_embedding (2048-dim) from Neo4j in vocab order
   (see arcd_train.py TODO comment and CLAUDE.md "Required changes" section)
4. Fix H_skill_raw persistence: save in state_dict at training, restore at inference
5. Re-run training — v4 defaults (mastery_weight=0.5, student_emb_dropout=0.3,
   d_skill=d=2048) are now correct:
   cd backend
   uv run python arcd_train.py \
       --data-dir ../knowledge_graph_builder/data/synthgen/<new_run_id> \
       --out-dir checkpoints/roma_synth_v4_2048
6. Update DEFAULT_CHECKPOINT_DIR in backend/arcd_agent/model_registry.py
   (already set to roma_synth_v4_2048)
7. Write all 5 GAT stage outputs (arcd_h_skill, arcd_h_question, arcd_h_video,
   arcd_h_reading, arcd_h_student) back to Neo4j at 2048-dim
8. Re-run inference walkthrough notebook to verify mastery is non-zero and
   OOV students print "→ UNK slot (idx=N)"
```

## Custom Slash Commands
Use `/project:fastapi`, `/project:shadcn-ui`, `/project:react-best-practices`, `/project:composition-patterns`, `/project:langgraph-docs`, `/project:alipos-api`, `/project:pdf` for skill-specific guidance. Plan commands available for implementation plans.
