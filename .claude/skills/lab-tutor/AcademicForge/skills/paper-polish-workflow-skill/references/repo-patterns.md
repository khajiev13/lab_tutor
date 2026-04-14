# Repo Scan Patterns

Scan heuristics for categorizing files in Python ML experiment repositories and mapping them to academic paper sections.

Scope: Python ML projects only (v2.0). Non-Python repo support deferred per ADVR-01.

## Quick Reference

| Category | Primary Section | Key File Types |
|---|---|---|
| documentation | Introduction | README.md, docs/**/*.md |
| config | Methods | *.yaml, *.yml, *.toml, *.json |
| results | Results and Discussion | results/**/*.csv, metrics.json |
| code | Methods | *.py, src/**/*.py, *.ipynb |
| figures | Results and Discussion | figures/**/*.png, plots/**/*.* |
| dependencies | Methods | requirements.txt, pyproject.toml |

## File Identification Patterns

| Glob | Category | Priority | Notes |
|---|---|---|---|
| `README.md`, `README.rst`, `README.txt` | documentation | 1 | Primary project description; highest priority |
| `docs/**/*.md` | documentation | 1 | Extended documentation |
| `*.yaml`, `*.yml`, `*.json`, `*.toml` | config | 2 | Hyperparameters, experiment settings |
| `*.ini`, `*.cfg`, `.env.example`, `Makefile` | config | 2 | Build and environment configuration |
| `results/**/*.csv`, `results/**/*.json` | results | 3 | Tabular experiment outputs |
| `results/**/*.xlsx`, `results/**/*.tsv` | results | 3 | Spreadsheet experiment outputs |
| `logs/**/*.log` | results | 3 | Training and evaluation logs |
| `*.csv` (root only), `metrics.json`, `scores.json` | results | 3 | Root-level result summaries |
| `*.py`, `src/**/*.py`, `scripts/**/*.py` | code | 4 | Source code and scripts |
| `*.ipynb` | code | 4 | Notebooks (see Ambiguity Rules) |
| `figures/**/*.png`, `figures/**/*.jpg` | figures | 5 | Static visualizations |
| `figures/**/*.svg`, `figures/**/*.pdf` | figures | 5 | Vector and PDF figures |
| `plots/**/*.*` | figures | 5 | Plot output directory |
| `*.png`, `*.jpg`, `*.svg` (root only) | figures | 5 | Root-level images |
| `requirements.txt`, `setup.py`, `setup.cfg` | dependencies | 6 | Python packaging and dependencies |
| `pyproject.toml`, `Pipfile` | dependencies | 6 | Modern Python packaging |
| `environment.yml`, `conda.yml` | dependencies | 6 | Conda environment specification |

Priority 1 = highest specificity. When a file matches multiple categories, use the lowest priority number (most specific wins).

## Category to Paper Section Mapping

| Category | Primary Section | Secondary Section | Notes |
|---|---|---|---|
| documentation | Introduction | Methods | README often describes both motivation and approach |
| config | Methods | - | Hyperparameters, model architecture choices, experiment settings |
| results | Results and Discussion | - | Tables, metrics, evaluation outputs |
| code | Methods | - | Algorithm implementation details, model architecture |
| figures | Results and Discussion | - | Visualizations of findings, plots |
| dependencies | Methods | - | Technology stack, reproducibility information |

## Ambiguity Rules

- **Jupyter notebooks** (`*.ipynb`): categorize as "code" by default. If located in `results/`, `figures/`, or `output/` directory, categorize by directory instead
- **Multiple category matches**: use the lowest priority number (most specific wins)
- **Hidden files and directories** (`.*`): skip entirely
- **Test files** (`test_*`, `*_test.py`, `tests/`): skip -- not relevant to paper content
- **Data files** (`*.h5`, `*.pkl`, `*.npy`, `*.pt`, `*.pth`): skip -- binary data, not directly readable for outline generation
- **`pyproject.toml` overlap**: matches both config (Priority 2) and dependencies (Priority 6). Categorize as dependencies -- its primary role is package specification

## Scan Depth

Scan root directory and one level of subdirectories (top 2 levels). Deeper paths require explicit user specification.

Directory names that indicate relevant content at the first subdirectory level:

| Directory | Expected Content |
|---|---|
| `src/` | Core source code modules |
| `scripts/` | Utility and execution scripts |
| `results/` | Experiment output data and metrics |
| `figures/` | Generated visualizations and plots |
| `logs/` | Training and evaluation logs |
| `data/` | Dataset references (skip binary files) |
| `models/` | Model definitions or saved checkpoints |
| `notebooks/` | Jupyter notebooks for exploration |
| `experiments/` | Experiment configurations and runs |
| `docs/` | Extended project documentation |
| `plots/` | Plot output files |

## Skip Rules

Files and directories to exclude from scan:

- Hidden files and directories (names starting with `.`)
- `__pycache__/`, `*.pyc`, `*.pyo` -- Python bytecode
- `node_modules/`, `.venv/`, `venv/`, `env/` -- virtual environments
- `.git/` -- version control internals
- `test_*`, `*_test.py`, `tests/` -- test files (not paper-relevant)
- Binary data files: `*.h5`, `*.pkl`, `*.npy`, `*.pt`, `*.pth`, `*.bin`

---

*Reference: references/repo-patterns.md*
*Conventions: references/skill-conventions.md*
