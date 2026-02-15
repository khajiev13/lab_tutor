## Plan: Stage 2 – Theory-Centric Book-Course Similarity Notebook

**TL;DR**: Create a new notebook [backend/app/modules/curricularalignmentarchitect/book_theory_matching.ipynb](backend/app/modules/curricularalignmentarchitect/book_theory_matching.ipynb) that implements the Stage 2 algorithm from the paper. It loads a downloaded PDF book, chunks it at **three granularities** (page-level, semantic sections, paragraph-level), embeds each using the existing `EmbeddingService`, loads course `text_evidence_embedding` vectors from Neo4j MENTIONS relationships, computes the max-similarity scoring algorithm, and outputs ranked results to a JSON file. This lets us compare which chunking strategy yields the best matching scores.

**Steps**

1. **Install PDF loader dependency**
   - Run `uv add pymupdf4llm` in [backend/](backend/) — `pymupdf4llm` wraps PyMuPDF and outputs clean Markdown from PDFs, ideal for academic textbooks. It also installs `pymupdf` as a dependency. This is the best option for structured academic text extraction.

2. **Create notebook Cell 1 — Imports & Configuration**
   - Reuse the `_env()` helper pattern from [workflow_v3.ipynb](backend/app/modules/curricularalignmentarchitect/workflow_v3.ipynb#L78) for env vars
   - Import `pymupdf4llm` for PDF loading
   - Import `RecursiveCharacterTextSplitter` from `langchain_text_splitters` (already a transitive dep of `langchain`)
   - Import the existing `EmbeddingService` from [backend/app/modules/embeddings/embedding_service.py](backend/app/modules/embeddings/embedding_service.py) — this wraps `OpenAIEmbeddings` with the project's XiaoCase API key, `text-embedding-3-small` model, 1536 dims, batching, and retries
   - Configure `BOOK_PATH` variable pointing to the PDF in [backend/data/books/](backend/data/books/)
   - Configure `COURSE_ID = 1`

3. **Cell 2 — Load & Extract PDF Text**
   - Use `pymupdf4llm.to_markdown(BOOK_PATH)` to extract clean Markdown text from the PDF
   - Display basic stats: page count, total characters, sample text

4. **Cell 3 — Three Chunking Strategies**
   - Use `RecursiveCharacterTextSplitter` with three configurations, all producing `Document` objects with metadata:
     - **Page-level**: `chunk_size=3000, chunk_overlap=200`, separators `["\n\n\n", "\n\n"]` — approximates one page per chunk
     - **Semantic sections**: `chunk_size=1500, chunk_overlap=200`, separators `["\n## ", "\n### ", "\n# ", "\n\n", "\n"]` — exploits Markdown headers from `pymupdf4llm` to split on chapter/section boundaries
     - **Paragraph-level**: `chunk_size=600, chunk_overlap=100`, separators `["\n\n", "\n", ". "]` — fine-grained
   - Print chunk counts and avg chunk length for each strategy

5. **Cell 4 — Embed Book Chunks**
   - Instantiate `EmbeddingService()` from the existing module (no config duplication)
   - For each chunking strategy, call `embedding_service.embed_documents(chunk_texts)` — this handles batching (64 per batch), retries, and dimension validation internally
   - Store as `dict[str, list[list[float]]]` keyed by strategy name
   - Print embedding counts and dimensions

6. **Cell 5 — Load Course Content from Neo4j ($Q_{theories}$)**
   - Connect to Neo4j using the same `_env()` pattern as [workflow_v3.ipynb cell 3](backend/app/modules/curricularalignmentarchitect/workflow_v3.ipynb#L381)
   - Query: `MATCH (c:CLASS {id: $cid})-[:HAS_DOCUMENT]->(d)-[r:MENTIONS]->(concept) RETURN r.text_evidence AS text, r.text_evidence_embedding AS embedding, concept.name AS concept_name, d.topic AS doc_topic`
   - This gives us the $Q_{theories}$ — the 352 text evidence embeddings representing what the course teaches
   - Validate all 352 embeddings are 1536-dim
   - Print stats: concept count, grouped by document

7. **Cell 6 — Compute Similarity Scores (Algorithm Implementation)**
   - Implement exactly the algorithm from the image:
     - For each chunking strategy ($P_{theories}$ = book chunk embeddings):
       - For each course theory $q_x \in Q_{theories}$:
         - $sim_{max} = \max_{p_y \in P_{theories}} \frac{q_x \cdot p_y}{\|q_x\| \|p_y\|}$ (cosine similarity)
         - $Score_{sum} = Score_{sum} + sim_{max}$
       - $\mathscr{S}_{final} = \frac{Score_{sum}}{|Q_{theories}|}$
   - Use `numpy` for efficient vectorized cosine similarity (dot product of normalized matrices)
   - Also track: for each course concept, which book chunk it matched best with (for interpretability)

8. **Cell 7 — Results Comparison & Visualization**
   - Table comparing three strategies: final score, avg similarity, median, min, max
   - Histogram of per-concept similarity distributions for each strategy
   - Top-10 and bottom-10 matched concepts for the best strategy (which concepts are covered vs. missing)

9. **Cell 8 — Export to JSON**
   - Save results to a JSON file in the notebook's directory (e.g., `book_theory_matching_results.json`)
   - Include: book path, chunking strategy scores, per-concept matches, metadata

**Verification**
- Run `uv add pymupdf4llm` in `backend/` to install the dependency
- Execute notebook cells sequentially — each cell prints validation stats
- Final JSON output should contain similarity scores for all three strategies
- Scores should be in [0, 1] range; expect 0.3–0.7 for a partially relevant book

**Decisions**
- **PyMuPDF4LLM over PyPDF**: PyMuPDF produces cleaner Markdown output from academic PDFs (preserves headers, tables, structure), which directly benefits the semantic section splitter since it can split on `## ` headers
- **`text_evidence_embedding` over `definition_embedding`**: Per user choice — text evidence captures the actual lecture content wording, closer to what students experience
- **Reuse `EmbeddingService` directly**: Avoids duplicating API key/model/batching config — just `from app.modules.embeddings.embedding_service import EmbeddingService` and call `embed_documents()`
- **Three strategies side-by-side**: Allows empirical comparison without committing to one approach upfront
- **`numpy` for similarity**: Vectorized matrix operations make the $O(|Q| \times |P|)$ similarity computation fast even with 352 × hundreds of chunks
