# Expected Outputs

These files are copied from the thesis job-fit evaluation runs.

- `expected_job_satisfaction_summary.csv`: 75 job-level portfolio scores from
  the primary DeepSeek judge run.
- `expected_job_requirement_ratings.csv`: 474 requirement-level ratings from
  the primary DeepSeek judge run.
- `expected_judge_robustness_summary.csv`: five-judge robustness summary.
- `expected_judge_robustness_table.tex`: LaTeX table generated from the
  robustness summary.

The expected files are reference outputs for comparison. Fresh reruns through
live LLM APIs may differ slightly because provider-side models can change, but
the evaluation contract, frozen inputs, and scoring rule are fixed here.
