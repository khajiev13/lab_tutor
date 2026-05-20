# Lab Tutor Job-Fit Evaluation Reproduction Bundle

This folder contains the frozen inputs, runnable code, and expected outputs for
the thesis job-fit evaluation. It is designed so readers can rerun the LLM judge
without access to the Lab Tutor Neo4j database.

GitHub folder:
<https://github.com/khajiev13/lab_tutor/tree/feat/course-readiness-prerequisite-review/evaluation>

## Folder Layout

- `input/job_fit_inputs.json` stores the exact three portfolios and 25 job
  postings used in the thesis evaluation.
- `input/judge_models.json` lists the five LLM judges used for the robustness
  check.
- `code/run_job_fit_evaluation.py` reruns the requirement-level LLM judge from
  the frozen JSON input.
- `code/summarize_judge_robustness.py` summarizes multiple reruns into the
  robustness table.
- `output/expected_*` files contain the outputs reported in the thesis.

## Frozen Protocol

The input bundle contains three bounded learner-profile portfolios:

- `course_only`: 100 canonical course skills.
- `book_student`: course skills plus 21 selected textbook-derived skills.
- `market_student`: course skills plus 34 selected market-derived skills.

The 25 job postings contain 158 total requirement strings. Each portfolio is
paired with each posting, giving 75 judge calls and 474 requirement-level
ratings per judge model.

## Run One Judge

Set an API key for an OpenAI-compatible endpoint:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.example.com/v1"
```

Then run one model:

```bash
python3 evaluation/code/run_job_fit_evaluation.py \
  --input evaluation/input/job_fit_inputs.json \
  --output-dir evaluation/output/runs/deepseek_v4_pro \
  --family DeepSeek \
  --model deepseek-v4-pro \
  --api-key-env OPENAI_API_KEY \
  --base-url "$OPENAI_BASE_URL"
```

The script writes:

- `job_satisfaction_summary.csv`
- `job_requirement_ratings.csv`
- `audit/*.json`
- `run_metadata.json`

## Run All Robustness Judges

The thesis robustness check used DeepSeek, Qwen, GLM, Kimi, and MiniMax. Repeat
the command above for each model listed in `input/judge_models.json`, changing
`--output-dir`, `--family`, and `--model` each time.

After those runs finish, summarize them:

```bash
python3 evaluation/code/summarize_judge_robustness.py \
  --runs-dir evaluation/output/runs \
  --output-csv evaluation/output/judge_robustness_summary.csv \
  --output-tex evaluation/output/judge_robustness_table.tex
```

## Expected Outputs

The files in `output/expected_*` are the thesis run outputs. Because LLM APIs
can change over time, new reruns may not be byte-identical, but the central
robustness claim should be evaluated by the same criterion used in the thesis:
within each judge, the Market portfolio should remain above the Course
portfolio on the same frozen posting set.
