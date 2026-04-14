# Body Generation Rules

Rules for generating academic paper body text from repo analysis. Used by `repo-to-paper-skill` Step 5.

Scope: Anti-hallucination annotations, claim classification, bilingual LaTeX formatting, and references.bib generation.

## Claim Classification

| Claim Type | Annotation Required | Example |
|---|---|---|
| Repo-derived (specific numbers, model names, dataset sizes, configurations) | `[SOURCE: file:line]` after the claim | `The model uses 500 estimators [SOURCE: config.yaml:12]` |
| Quantitative result (metric value unknown) | `[RESULTS NEEDED]` placeholder | `The model achieved an R-squared of [RESULTS NEEDED]` |
| Specific metric (metric name known, value unknown) | `[EXACT VALUE: metric]` placeholder | `The RMSE was [EXACT VALUE: RMSE]` |
| Background/context prose (general domain knowledge, problem framing) | None -- write as normal academic text | `Urban heat islands result from impervious surface replacement` |

- Every repo-derived specific claim MUST have a `[SOURCE: file:line]` annotation. The annotation references the actual repo file and line number where the data was found during Step 1 scan or Step 5 content reading.
- Never state a specific number, model name, dataset size, or configuration value without a `[SOURCE:]` annotation.
- Background/context prose does not require annotation -- general domain knowledge used for framing and transitions is acceptable.

## Citation Integration

- All citations use `\cite{citationkey}` inline format
- Citation keys MUST only reference papers present in `{repo_path}/.paper-refs/*.md` files
- If a claim needs a citation but no `.paper-refs/` entry supports it: use `[CITATION NEEDED]` placeholder
- When `.paper-refs/` directory is missing entirely (Step 2.5 was skipped): ALL citation positions use `[CITATION NEEDED]`
- Never cite from Claude's background knowledge -- this is a strict source boundary

## Bilingual LaTeX Format

Per `references/bilingual-output.md`, body text uses LaTeX comment format with paragraph markers.

```latex
% --- Paragraph 1 ---
% Chinese academic translation of the paragraph below.
% Technical terms preserved with English in parentheses: 城市热岛效应（urban heat island effect）.
English paragraph text with \cite{key} citations and [SOURCE: file:line] annotations.

% --- Paragraph 2 ---
% Next Chinese paragraph.
Next English paragraph.
```

- Paragraph markers (`% --- Paragraph N ---`) are REQUIRED (per bilingual-output.md)
- Chinese uses academic written register (学术书面语): "本研究提出了..." not "我们做了..."
- Technical terms: preserve English with Chinese explanation in parentheses
- Chinese translation includes the same `\cite{key}` references as the English text
- When bilingual mode is OFF (opt-out keywords detected): omit all `%` Chinese comment lines and paragraph markers

## CEUS Writing Style

Full CEUS contract at `references/journals/ceus.md`. Key rules for body generation:

- Tense: past tense for methods and results sections; present tense acceptable in discussion for broader implications
- Verbs: prefer `suggest`, `indicate`, `show` unless stronger causal evidence is available
- Avoid: `novel`, `groundbreaking`, `revolutionary`, or similar self-promotional adjectives
- Avoid: empty smart-city framing not used in the analysis
- Avoid: over-generalized policy claims unsupported by the empirical setting
- Maintain geography/urban-systems perspective throughout

## references.bib Generation

Algorithm:

1. Read all files matching `{repo_path}/.paper-refs/*.md`
2. For each file, extract all content between ` ```bibtex ` and ` ``` ` markers
3. Parse each BibTeX entry to extract the citation key (the identifier after `@article{`, `@inproceedings{`, etc.)
4. Deduplicate: if the same citation key appears in multiple files, keep the first occurrence only
5. Write all unique entries to `{repo_path}/.paper-output/references.bib`
6. Display count: "Generated references.bib with N unique entries from M ref files."

Generate references.bib ONCE after ALL selected sections are confirmed. Do NOT generate per-section.

## Output File Structure

Directory: `{repo_path}/.paper-output/`

One `.tex` file per H1 section, named by section topic in lowercase (e.g., `introduction.tex`, `methods.tex`, `results.tex`, `discussion.tex`, `conclusion.tex`).

Each `.tex` file contains `\section{}`, `\subsection{}`, `\subsubsection{}` LaTeX heading commands followed by body paragraphs.

Complete example `.tex` file:

```latex
\section{Introduction}

% --- Paragraph 1 ---
% 城市热岛效应（urban heat island effect）已成为城市规划和公共健康研究中日益重要的议题
% \cite{smith2023urban}。理解街道层面的语义特征如何影响热环境，
% 对于循证城市设计至关重要 \cite{li2022spatial}。
The urban heat island effect has become increasingly important in urban planning
and public-health research \cite{smith2023urban}. Understanding how street-level
semantic features influence the thermal environment is essential for evidence-based
urban design \cite{li2022spatial}.

\subsection{Research Background}

% --- Paragraph 2 ---
% 近年来，遥感和街景图像的结合为城市热环境分析提供了新的视角 [CITATION NEEDED]。
% 梯度提升模型已被广泛应用于城市环境预测任务 \cite{zhang2021gradient}。
Recent advances in combining remote sensing with street-view imagery have provided
new perspectives for urban thermal environment analysis [CITATION NEEDED].
Gradient boosting models have been widely applied to urban environment prediction
tasks \cite{zhang2021gradient}.

\subsubsection{Data Characteristics}

% --- Paragraph 3 ---
% 本研究使用的数据集包含12,000个采样点 [SOURCE: README.md:45]，
% 覆盖研究区域内所有主要街道。模型配置包括500棵决策树 [SOURCE: config.yaml:12]，
% 学习率为0.01 [SOURCE: config.yaml:13]。
The dataset used in this study comprises 12,000 sampling points [SOURCE: README.md:45],
covering all major streets within the study area. The model configuration includes
500 estimators [SOURCE: config.yaml:12] with a learning rate of 0.01
[SOURCE: config.yaml:13]. The model achieved an R-squared of [RESULTS NEEDED]
on the held-out test set, with an RMSE of [EXACT VALUE: RMSE].
```

---

*Reference: references/body-generation-rules.md*
*Conventions: references/skill-conventions.md*
