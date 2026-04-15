# Conference Paper Algorithm Drafts

These LaTeX algorithm blocks are aligned with the current implementation in the repo:

- book skill collection: `backend/app/modules/curricularalignmentarchitect/chapter_extraction`
- market skill collection: `backend/app/modules/marketdemandanalyst`
- reading/video fetching: `backend/app/modules/student_learning_path`, `backend/app/core/resource_pipeline`, `backend/app/modules/textualresourceanalyst`, `backend/app/modules/visualcontentevaluator`

If the main paper only keeps **two algorithm tables**, the best fit is:

1. Algorithm 1 for the textbook-side skill bank
2. Algorithm 2 for the market-side skill bank

Algorithm 3 is still useful, but it fits best in the resource-application subsection or in an appendix/supplement.

The third algorithm below intentionally focuses on **reading and video retrieval only**. The same student learning-path graph also generates questions, but that branch is omitted here because the requested conference-paper formula is about resource fetching.

## Algorithm 1

```latex
\begin{algorithm}[t]
\caption{\textbf{Curricular Alignment Architect: Book-Skill Bank Construction}}
\label{alg:book-skill-bank}
\begin{algorithmic}[1]
\bfseries
\Require Teacher-approved books $\mathcal{B}_{sel}$, course chapter scaffold $\mathcal{C}$, course subject $\sigma$
\Ensure Book skill bank $\mathcal{S}_{B}$ mapped into course chapters

\State \textbf{// Stage 1: Parallel Chapter-Level Skill Collection}
\For{each $B_i \in \mathcal{B}_{sel}$}
    \State $\{ch_1, \dots, ch_{N_i}\} \leftarrow \text{LoadExtractedChapters}(B_i)$
    \For{each unfinished chapter $ch_j$ \textbf{in parallel}}
        \State $R_j \leftarrow \text{LLM}_{skills}(ch_j,\ \sigma)$
        \Statex \hspace{\algorithmicindent} $\triangleright$ extract summary, skills, and concepts
        \State $F_j \leftarrow \text{LLM}_{judge}(R_j,\ ch_j)$
        \If{$F_j.\text{verdict} = \texttt{NEEDS\_REVISION}$}
            \State $R_j \leftarrow \text{LLM}_{revise}(R_j,\ F_j.\text{issues},\ ch_j)$
            \Statex \hspace{\algorithmicindent} $\triangleright$ allow at most one revision
        \EndIf
        \State $(\mathbf{e}^{name}_j,\ \mathbf{e}^{desc}_j) \leftarrow \text{EmbedBatch}(R_j.\text{skills})$
        \State $\text{UpdateKnowledgeGraph}(ch_j,\ R_j)$
        \Statex \hspace{\algorithmicindent} $\triangleright$ write skills and concepts to the knowledge graph
    \EndFor
\EndFor

\State
\State \textbf{// Stage 2: Curriculum Mapping of Book Skills}
\State $\mathcal{C} \leftarrow \text{LoadCourseChapters}()$
\State $\mathcal{H} \leftarrow \text{LoadBookChaptersWithSkills}(\mathcal{B}_{sel})$
\For{each book chapter $h \in \mathcal{H}$}
    \State $\mathcal{M}_h \leftarrow \text{LLM}_{map}(h.\text{skills},\ \mathcal{C})$
    \Statex \hspace{\algorithmicindent} $\triangleright$ map skills to course chapters
    \State $\text{WriteMappings}(\mathcal{M}_h)$
    \Statex \hspace{\algorithmicindent} $\triangleright$ write chapter mappings to the knowledge graph
\EndFor

\State
\State $\mathcal{S}_{B} \leftarrow \{s \mid s:\texttt{BOOK\_SKILL},\ s \xrightarrow{\texttt{MAPPED\_TO}} c,\ c \in \mathcal{C}\}$
\State \Return $\mathcal{S}_{B}$
\end{algorithmic}
\end{algorithm}
```

## Algorithm 2

```latex
\begin{algorithm}[t]
\caption{\textbf{Market Demand Analyst: Market-Skill Bank Construction}}
\label{alg:market-skill-bank}
\begin{algorithmic}[1]
\bfseries
\Require Course context $\mathcal{D}$, approved search terms $\mathcal{T}$, curriculum graph $\mathcal{G}_{course}$
\Ensure Cleaned market skill bank $\mathcal{S}_{M}$ linked to chapters, jobs, and concepts

\State \textbf{// Stage 1: Job Collection and Teacher Scoping}
\For{each search term $t \in \mathcal{T}$ and site $u \in \{\text{Indeed}, \text{LinkedIn}\}$ \textbf{in parallel}}
    \State $\mathcal{J}_{t,u} \leftarrow \text{FetchJobs}(t,\ u)$
\EndFor
\State $\mathcal{J}_{raw} \leftarrow \text{DedupByTitleCompany}\Bigl(\bigcup_{t,u}\mathcal{J}_{t,u}\Bigr)$
\State $\mathcal{G}_{job} \leftarrow \text{GroupByNormalizedTitle}(\mathcal{J}_{raw})$
\State $\mathcal{J}_{sel} \leftarrow \text{TeacherSelectGroups}(\mathcal{G}_{job})$

\State
\State \textbf{// Stage 2: Parallel Skill Extraction and Canonicalization}
\For{each job $j \in \mathcal{J}_{sel}$ \textbf{in parallel}}
    \State $\mathcal{E}_j \leftarrow \text{LLM}_{extract}(j.\text{description})$
    \Statex \hspace{\algorithmicindent} $\triangleright$ extract competency statements
\EndFor
\State $\mathcal{S}_{raw} \leftarrow \text{Aggregate}\Bigl(\bigcup_j \mathcal{E}_j\Bigr)$
\For{each skill $s \in \mathcal{S}_{raw}$}
    \State $f(s) \leftarrow \text{JobFrequency}(s)$
    \State $p(s) \leftarrow 100 \cdot f(s) / |\mathcal{J}_{sel}|$
\EndFor
\If{$10 < |\mathcal{S}_{raw}| \leq 150$}
    \State $\mathcal{S}_{llm} \leftarrow \text{LLM}_{merge}(\mathcal{S}_{raw})$
\Else
    \State $\mathcal{S}_{llm} \leftarrow \mathcal{S}_{raw}$
\EndIf
\State $\mathcal{S}_{ext} \leftarrow \text{EmbedDedup}(\mathcal{S}_{llm},\ \tau{=}0.92)$

\State
\State \textbf{// Stage 3: Teacher Curation and Curriculum Mapping}
\State $\mathcal{S}_{cur} \leftarrow \text{TeacherCurateByNameCategoryTopN}(\mathcal{S}_{ext})$
\For{each curated skill $s \in \mathcal{S}_{cur}$}
    \State $\text{cov}(s) \leftarrow \text{CheckGraphCoverage}(s,\ \texttt{BOOK\_SKILL},\ \texttt{MARKET\_SKILL},\ \texttt{CONCEPT})$
    \State $(\text{status}(s),\ ch^{*}(s),\ \rho(s)) \leftarrow \text{LLM}_{map}(s,\ \text{cov}(s),\ \mathcal{G}_{course})$
    \Statex \hspace{\algorithmicindent} $\triangleright$ assign status and best-fit chapter
\EndFor
\State $\mathcal{M} \leftarrow \text{SaveCurriculumMapping}(\mathcal{S}_{cur})$
\Statex \hspace{\algorithmicindent} $\triangleright$ keep one mapping row per skill

\State
\State \textbf{// Stage 4: Redundancy Cleaning and Concept Linking}
\For{each course chapter $c$ with mapped skills}
    \State $\mathcal{S}^{new}_c \leftarrow \text{MappedSkills}(\mathcal{M}, c)$
    \State $\mathcal{S}^{exist}_c \leftarrow \text{LoadExistingChapterSkills}(c)$
    \State $(\mathcal{K}_c,\ \mathcal{D}_c) \leftarrow \text{LLM}_{clean}(\mathcal{S}^{new}_c,\ \mathcal{S}^{exist}_c)$
    \Statex \hspace{\algorithmicindent} $\triangleright$ keep additive skills only
\EndFor
\State $\mathcal{S}_{keep} \leftarrow \bigcup_c \mathcal{K}_c$
\For{each $s \in \mathcal{S}_{keep}$}
    \State $(\mathcal{C}^{exist}_s,\ \mathcal{C}^{new}_s) \leftarrow \text{LLM}_{concept}(s,\ ch^{*}(s),\ \text{JobEvidence}(s))$
    \State $\text{UpdateKnowledgeGraph}(s,\ ch^{*}(s),\ \text{JobEvidence}(s))$
    \Statex \hspace{\algorithmicindent} $\triangleright$ write skills and links to the knowledge graph
\EndFor

\State
\State $\mathcal{S}_{M} \leftarrow \mathcal{S}_{keep}$
\State \Return $\mathcal{S}_{M}$
\end{algorithmic}
\end{algorithm}
```

## Algorithm 3

```latex
\begin{algorithm}[t]
\caption{\textbf{Skill-Conditioned Reading and Video Retrieval}}
\label{alg:resource-fetch}
\begin{algorithmic}[1]
\bfseries
\Require Selected skills $\mathcal{S}_{sel}$, skill profiles $\mathcal{P}$, curriculum graph $\mathcal{G}$
\Ensure Reading resources $\mathcal{R}$ and video resources $\mathcal{V}$ linked to skills

\State \textbf{// Stage 1: Incremental Dispatch}
\For{each selected skill $s \in \mathcal{S}_{sel}$}
    \State $(h_R(s),\ h_V(s)) \leftarrow \text{CheckExistingResources}(s)$
    \If{$\neg h_R(s)$ or $\neg h_V(s)$}
        \State $\text{DispatchWorker}(s)$
    \EndIf
\EndFor

\State
\State \textbf{// Stage 2: Per-Skill Resource Worker}
\For{each skill $s$ needing work \textbf{in parallel}}
    \If{$\neg h_R(s)$}
        \State $\{q^{R}_{1}, \dots, q^{R}_{m}\} \leftarrow \text{LLM}^{R}_{query}(\mathcal{P}(s))$
        \Comment{$4 \leq m \leq 6$, text-oriented queries}
        \State $\mathcal{U}^{R} \leftarrow \text{SearchTextWeb}(q^{R}_{1:m})$
        \Comment{blacklist video/paywalled domains}
        \State $\widehat{\mathcal{U}}^{R} \leftarrow \text{EmbeddingFilter}(\mathcal{P}(s),\ \mathcal{U}^{R},\ k{=}20)$
        \For{each candidate reading $r \in \widehat{\mathcal{U}}^{R}$}
            \State $(C_{rec}, C_{cov}, C_{ped}, C_{depth}, C_{src}) \leftarrow \text{LLM}^{R}_{score}(r,\ \mathcal{P}(s))$
            \State $C_{emb}(r) \leftarrow \text{MeanCosine}(r,\ \mathcal{P}(s).\text{concept\_embeddings})$
            \State $S^{R}(r) \leftarrow 0.15C_{rec} + 0.25C_{cov} + 0.15C_{emb} + 0.20C_{ped} + 0.15C_{depth} + 0.10C_{src}$
        \EndFor
        \State $\mathcal{R}_{s} \leftarrow \text{CoverageMaxTopK}(\widehat{\mathcal{U}}^{R},\ S^{R},\ k{=}3,\ \text{min\_types}{=}2)$
        \State $\text{UpdateKnowledgeGraph}(s,\ \mathcal{R}_{s})$
    \EndIf

    \If{$\neg h_V(s)$}
        \State $\{q^{V}_{1}, \dots, q^{V}_{n}\} \leftarrow \text{LLM}^{V}_{query}(\mathcal{P}(s))$
        \Comment{$4 \leq n \leq 6$, YouTube-focused queries with recency signal}
        \State $\mathcal{U}^{V} \leftarrow \text{SearchYouTube}(q^{V}_{1:n})$
        \State $\widehat{\mathcal{U}}^{V} \leftarrow \text{EmbeddingFilter}(\mathcal{P}(s),\ \mathcal{U}^{V},\ k{=}20)$
        \For{each candidate video $v \in \widehat{\mathcal{U}}^{V}$}
            \State $(C_{rec}, C_{cov}, C_{ped}, C_{depth}, C_{prod}) \leftarrow \text{LLM}^{V}_{score}(v,\ \mathcal{P}(s))$
            \State $C_{emb}(v) \leftarrow \text{MeanCosine}(v,\ \mathcal{P}(s).\text{concept\_embeddings})$
            \State $S^{V}(v) \leftarrow 0.15C_{rec} + 0.25C_{cov} + 0.15C_{emb} + 0.20C_{ped} + 0.15C_{depth} + 0.10C_{prod}$
        \EndFor
        \State $\mathcal{V}_{s} \leftarrow \text{CoverageMaxTopK}(\widehat{\mathcal{U}}^{V},\ S^{V},\ k{=}3,\ \text{min\_types}{=}2)$
        \State $\text{UpdateKnowledgeGraph}(s,\ \mathcal{V}_{s})$
    \EndIf
\EndFor

\State
\State $\mathcal{R} \leftarrow \bigcup_{s \in \mathcal{S}_{sel}} \mathcal{R}_{s}$
\State $\mathcal{V} \leftarrow \bigcup_{s \in \mathcal{S}_{sel}} \mathcal{V}_{s}$
\State \Return $\mathcal{R}, \mathcal{V}$
\end{algorithmic}
\end{algorithm}
```
