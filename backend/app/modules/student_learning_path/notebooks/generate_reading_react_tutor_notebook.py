from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf

NOTEBOOK_FILENAME = "reading_react_tutor.ipynb"


def markdown_cell(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(dedent(source).strip() + "\n")


def code_cell(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(dedent(source).strip() + "\n")


def build_notebook() -> nbf.NotebookNode:
    cells: list[nbf.NotebookNode] = [
        markdown_cell(
            """
            # Reading ReAct Tutor Prototype

            This notebook prototypes a **reading-only ReAct tutor** for Lab Tutor.

            It loads one student, one course, one mapped skill, and one reading from Neo4j, fetches the reading over HTTP, extracts article markdown, chunks the text, and runs a grounded tutor agent over the extracted passages.

            The notebook is intentionally graph-first:

            - discover candidate `(student_id, course_id, reading_id)` sessions from Neo4j
            - load one canonical reading session bundle
            - fetch article content from the selected reading URL
            - tutor strictly from retrieved reading passages plus student/course context

            This is a notebook prototype only. It does **not** implement backend routes or a browser UI.
            """
        ),
        markdown_cell(
            """
            ## What This Notebook Demonstrates

            The prototype is designed to answer one concrete product question:

            **Can a reading-page tutor fetch the reading, ground itself in the extracted article content, and adapt to the current student's course and skill context?**

            Notebook v1 constraints:

            - readings only, no videos
            - fail closed if the article cannot be extracted
            - no persistence outside the running notebook kernel
            - no fallback tutoring from snippet-only metadata
            """
        ),
        code_cell(
            """
            from __future__ import annotations

            import asyncio
            import json
            import os
            import re
            import sys
            import threading
            from collections import Counter
            from pathlib import Path
            from queue import Queue
            from textwrap import shorten

            import pandas as pd
            from IPython.display import Markdown, display
            from dotenv import load_dotenv
            from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
            from langchain_core.tools import tool
            from langchain_openai import ChatOpenAI
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from langgraph.prebuilt import create_react_agent
            from neo4j import Driver, GraphDatabase

            NOTEBOOK_DIR = None
            cwd = Path.cwd().resolve()
            search_roots = [cwd, *cwd.parents]
            for root in search_roots:
                direct_generator = root / "generate_reading_react_tutor_notebook.py"
                repo_generator = (
                    root
                    / "backend"
                    / "app"
                    / "modules"
                    / "student_learning_path"
                    / "notebooks"
                    / "generate_reading_react_tutor_notebook.py"
                )
                if direct_generator.exists():
                    NOTEBOOK_DIR = root
                    break
                if repo_generator.exists():
                    NOTEBOOK_DIR = repo_generator.parent
                    break

            if NOTEBOOK_DIR is None:
                raise RuntimeError(
                    "Could not locate the student learning path notebook directory."
                )

            REPO_ROOT = None
            for candidate in [NOTEBOOK_DIR, *NOTEBOOK_DIR.parents]:
                if (candidate / "backend").exists() and (candidate / "frontend").exists():
                    REPO_ROOT = candidate
                    break

            if REPO_ROOT is None:
                raise RuntimeError("Could not locate the Lab Tutor repo root.")

            backend_path = REPO_ROOT / "backend"
            if str(backend_path) not in sys.path:
                sys.path.insert(0, str(backend_path))

            load_dotenv(REPO_ROOT / ".env")

            from app.core.settings import settings
            from app.modules.student_learning_path.reader_extractor import (
                extract_reading_markdown,
            )

            pd.set_option("display.max_colwidth", 200)
            pd.set_option("display.max_rows", 100)

            print(f"Repo root: {REPO_ROOT}")
            print(f"Notebook dir: {NOTEBOOK_DIR}")
            """
        ),
        markdown_cell(
            """
            ## Configuration

            Set the target student, course, and reading here.

            Rules:

            - use either `STUDENT_ID` or `STUDENT_EMAIL`
            - `READING_URL_OVERRIDE` is optional and only for debugging
            - Neo4j / LLM overrides default to the repo `.env`

            Recommended workflow:

            1. run the discovery cells
            2. pick a `(student_id, course_id, reading_id)` combination
            3. load the session bundle
            4. fetch and chunk the reading
            5. initialize the thread
            6. chat with the tutor
            """
        ),
        code_cell(
            """
            COURSE_ID = None
            STUDENT_ID = None
            STUDENT_EMAIL = None
            READING_ID = None

            READING_URL_OVERRIDE = None

            DISCOVERY_LIMIT = 50
            CHUNK_SIZE = 1200
            CHUNK_OVERLAP = 200
            DEFAULT_CHUNK_SEARCH_K = 4
            PROMPT_MESSAGE_WINDOW = 12

            NEO4J_URI = None
            NEO4J_USERNAME = None
            NEO4J_PASSWORD = None
            NEO4J_DATABASE = None

            LLM_API_KEY = None
            LLM_BASE_URL = None
            LLM_MODEL = None

            USER_MESSAGE = "Please summarize this reading and then quiz me on the key ideas."
            DEBUG_QUERY = "core ideas and definitions"
            """
        ),
        markdown_cell(
            """
            ## Driver And Low-Level Helpers

            These helpers keep the notebook self-contained while still defaulting to the repo's configured Neo4j and LLM settings.
            """
        ),
        code_cell(
            """
            STOPWORDS = {
                "a",
                "an",
                "and",
                "are",
                "as",
                "at",
                "be",
                "by",
                "for",
                "from",
                "how",
                "in",
                "is",
                "it",
                "of",
                "on",
                "or",
                "that",
                "the",
                "this",
                "to",
                "what",
                "when",
                "which",
                "with",
                "you",
            }
            TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
            HEADING_RE = re.compile(r"^(#+)\\s+(.*)$")


            def _resolve_setting(override, *fallbacks):
                if override not in (None, ""):
                    return override
                for candidate in fallbacks:
                    if candidate not in (None, ""):
                        return candidate
                return None


            def create_neo4j_driver(
                *,
                neo4j_uri: str | None = None,
                neo4j_username: str | None = None,
                neo4j_password: str | None = None,
            ) -> Driver:
                uri = _resolve_setting(neo4j_uri, settings.neo4j_uri, os.getenv("LAB_TUTOR_NEO4J_URI"))
                username = _resolve_setting(
                    neo4j_username,
                    settings.neo4j_username,
                    os.getenv("LAB_TUTOR_NEO4J_USERNAME"),
                )
                password = _resolve_setting(
                    neo4j_password,
                    settings.neo4j_password,
                    os.getenv("LAB_TUTOR_NEO4J_PASSWORD"),
                )
                if not (uri and username and password):
                    raise RuntimeError(
                        "Neo4j connection details are missing. Configure the repo .env "
                        "or set NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD."
                    )
                return GraphDatabase.driver(uri, auth=(username, password))


            def get_neo4j_database(override: str | None = None) -> str:
                return str(
                    _resolve_setting(
                        override,
                        settings.neo4j_database,
                        os.getenv("LAB_TUTOR_NEO4J_DATABASE"),
                        "neo4j",
                    )
                )


            def create_llm() -> ChatOpenAI:
                model = _resolve_setting(LLM_MODEL, settings.llm_agent_model, settings.llm_model)
                base_url = _resolve_setting(LLM_BASE_URL, settings.llm_base_url)
                api_key = _resolve_setting(LLM_API_KEY, settings.llm_api_key, os.getenv("LAB_TUTOR_LLM_API_KEY"))
                if not (model and base_url and api_key):
                    raise RuntimeError(
                        "LLM settings are incomplete. Configure the repo .env or set "
                        "LLM_API_KEY / LLM_BASE_URL / LLM_MODEL."
                    )
                return ChatOpenAI(
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    temperature=0,
                    streaming=False,
                    timeout=settings.llm_timeout_seconds,
                    extra_body={"enable_thinking": False},
                )


            def _json(data) -> str:
                return json.dumps(data, indent=2, ensure_ascii=False)


            def _compact_text(value: str, *, width: int = 140) -> str:
                return shorten(" ".join(str(value).split()), width=width, placeholder="…")


            NEO4J_DRIVER = create_neo4j_driver(
                neo4j_uri=NEO4J_URI,
                neo4j_username=NEO4J_USERNAME,
                neo4j_password=NEO4J_PASSWORD,
            )
            NEO4J_DATABASE_RESOLVED = get_neo4j_database(NEO4J_DATABASE)

            print(f"Neo4j database: {NEO4J_DATABASE_RESOLVED}")
            """
        ),
        markdown_cell(
            """
            ## Discovery

            This discovery query lists reading sessions that are already visible in the student's course path.
            """
        ),
        code_cell(
            '''
            DISCOVER_READING_SESSIONS_QUERY = """
            MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS)
            MATCH (u)-[:SELECTED_SKILL]->(sk:SKILL)-[:HAS_READING]->(rr:READING_RESOURCE)
            MATCH (cl)-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)<-[:MAPPED_TO]-(sk)
            WHERE ($course_id IS NULL OR cl.id = $course_id)
              AND ($student_id IS NULL OR u.id = $student_id)
              AND ($student_email IS NULL OR u.email = $student_email)
            RETURN DISTINCT
                u.id AS student_id,
                u.email AS student_email,
                trim(coalesce(u.first_name, '') + ' ' + coalesce(u.last_name, '')) AS student_name,
                cl.id AS course_id,
                cl.title AS course_title,
                ch.chapter_index AS chapter_index,
                ch.title AS chapter_title,
                sk.name AS skill_name,
                rr.id AS reading_id,
                rr.title AS reading_title,
                rr.url AS reading_url,
                rr.domain AS domain,
                rr.resource_type AS resource_type,
                rr.final_score AS final_score,
                (
                    toLower(coalesce(rr.resource_type, '')) CONTAINS 'pdf'
                    OR toLower(coalesce(rr.url, '')) CONTAINS '.pdf'
                    OR toLower(coalesce(rr.search_result_url, '')) CONTAINS '.pdf'
                ) AS looks_like_pdf
            ORDER BY student_id, course_id, chapter_index, skill_name, reading_title
            LIMIT $limit
            """


            def discover_reading_sessions(
                *,
                course_id: int | None = None,
                student_id: int | None = None,
                student_email: str | None = None,
                limit: int = DISCOVERY_LIMIT,
            ) -> pd.DataFrame:
                with NEO4J_DRIVER.session(database=NEO4J_DATABASE_RESOLVED) as session:
                    rows = [
                        record.data()
                        for record in session.run(
                            DISCOVER_READING_SESSIONS_QUERY,
                            course_id=course_id,
                            student_id=student_id,
                            student_email=student_email,
                            limit=int(limit),
                        )
                    ]
                return pd.DataFrame(rows)
            '''
        ),
        code_cell(
            """
            discovery_df = discover_reading_sessions(
                course_id=COURSE_ID,
                student_id=STUDENT_ID,
                student_email=STUDENT_EMAIL,
            )
            if discovery_df.empty:
                print("No reading sessions matched the current discovery filters.")
            else:
                display(discovery_df)
            """
        ),
        markdown_cell(
            """
            ## Session Loader

            This is the canonical graph-first query used for the selected reading tutoring session.
            """
        ),
        code_cell(
            '''
            READING_SESSION_QUERY = """
            MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS)
            WHERE ($student_id IS NOT NULL AND u.id = $student_id)
               OR ($student_id IS NULL AND u.email = $student_email)

            MATCH (u)-[sel:SELECTED_SKILL]->(sk:SKILL)-[:HAS_READING]->(rr:READING_RESOURCE {id: $reading_id})
            MATCH (cl)-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)<-[:MAPPED_TO]-(sk)
            WHERE cl.id = $course_id

            RETURN {
              student: u { .id, .email, .first_name, .last_name },
              course: cl { .id, .title, .description },
              chapter: ch { .chapter_index, .title, .description, .learning_objectives },
              skill: sk {
                .name,
                .description,
                source: sel.source,
                skill_type: CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END,
                concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c { .name, .description }],
                questions: COLLECT {
                  MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
                  WHERE q.difficulty IN ['easy', 'medium', 'hard']
                    AND size(coalesce(q.options, [])) > 0
                  RETURN q { .id, .text, .difficulty, options: coalesce(q.options, []) } AS question
                  ORDER BY CASE q.difficulty
                    WHEN 'easy' THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'hard' THEN 2
                  END
                }
              },
              reading: rr {
                .id, .title, .url, .domain, .snippet, .search_content,
                .resource_type, .final_score, .search_result_url,
                .search_result_domain, .source_engine, .source_engines,
                .search_metadata_json,
                concepts_covered: coalesce(rr.concepts_covered, [])
              }
            } AS payload
            LIMIT 1
            """


            def load_reading_session_bundle(
                student_id: int | None,
                student_email: str | None,
                course_id: int,
                reading_id: str,
            ) -> dict:
                if student_id is None and not student_email:
                    raise ValueError("Set STUDENT_ID or STUDENT_EMAIL before loading a session.")
                if course_id is None:
                    raise ValueError("Set COURSE_ID before loading a session.")
                if not reading_id:
                    raise ValueError("Set READING_ID before loading a session.")

                with NEO4J_DRIVER.session(database=NEO4J_DATABASE_RESOLVED) as session:
                    record = session.run(
                        READING_SESSION_QUERY,
                        student_id=student_id,
                        student_email=student_email,
                        course_id=int(course_id),
                        reading_id=str(reading_id),
                    ).single()

                if record is None:
                    raise ValueError(
                        "No reading session matched the current STUDENT / COURSE / READING selection."
                    )

                payload = record["payload"]
                payload["selected_by"] = {
                    "student_id": student_id,
                    "student_email": student_email,
                    "course_id": int(course_id),
                    "reading_id": str(reading_id),
                }
                return payload
            '''
        ),
        code_cell(
            """
            CURRENT_SESSION_BUNDLE = None

            if COURSE_ID and READING_ID and (STUDENT_ID is not None or STUDENT_EMAIL):
                CURRENT_SESSION_BUNDLE = load_reading_session_bundle(
                    student_id=STUDENT_ID,
                    student_email=STUDENT_EMAIL,
                    course_id=int(COURSE_ID),
                    reading_id=str(READING_ID),
                )
                display(Markdown("### Loaded Reading Session Bundle"))
                display(Markdown(f"```json\\n{_json(CURRENT_SESSION_BUNDLE)}\\n```"))
            else:
                print(
                    "Set COURSE_ID, READING_ID, and STUDENT_ID or STUDENT_EMAIL in the configuration cell "
                    "before loading a session bundle."
                )
            """
        ),
        markdown_cell(
            """
            ## Reading Fetch

            The notebook uses the existing async `reader_extractor` helper and fails closed if article extraction is not successful.
            """
        ),
        code_cell(
            """
            LAST_READING_FETCH = None


            def _run_async_sync(coro):
                queue: Queue = Queue(maxsize=1)

                def _runner():
                    try:
                        value = asyncio.run(coro)
                    except Exception as exc:  # pragma: no cover - notebook runtime helper
                        queue.put((False, exc))
                    else:
                        queue.put((True, value))

                thread = threading.Thread(target=_runner, daemon=True)
                thread.start()
                thread.join()

                ok, payload = queue.get()
                if ok:
                    return payload
                raise payload


            def fetch_reading_markdown_for_session(
                bundle: dict,
                url_override: str | None = None,
            ) -> str:
                global LAST_READING_FETCH

                reading = bundle["reading"]
                resolved_url = str(url_override or reading.get("url") or reading.get("search_result_url") or "").strip()
                if not resolved_url:
                    raise RuntimeError("The selected reading does not have a usable URL.")

                result = _run_async_sync(extract_reading_markdown(resolved_url))
                LAST_READING_FETCH = {
                    "resolved_url": resolved_url,
                    "status": result.status,
                }

                if result.status != "ready":
                    LAST_READING_FETCH["error_message"] = result.error_message
                    raise RuntimeError(result.error_message)

                LAST_READING_FETCH["char_count"] = len(result.content_markdown)
                return result.content_markdown
            """
        ),
        code_cell(
            """
            CURRENT_READING_MARKDOWN = None

            if CURRENT_SESSION_BUNDLE is None:
                print("Load a reading session bundle first.")
            else:
                try:
                    CURRENT_READING_MARKDOWN = fetch_reading_markdown_for_session(
                        CURRENT_SESSION_BUNDLE,
                        url_override=READING_URL_OVERRIDE,
                    )
                    print(
                        "Reading extraction succeeded:",
                        f"{len(CURRENT_READING_MARKDOWN)} characters of markdown",
                    )
                except Exception as exc:
                    CURRENT_READING_MARKDOWN = None
                    print("Reading extraction failed:", str(exc))
                    if LAST_READING_FETCH is not None:
                        display(Markdown(f"```json\\n{_json(LAST_READING_FETCH)}\\n```"))
            """
        ),
        markdown_cell(
            """
            ## Chunking

            The extracted article is split into overlapping chunks. Each chunk stores a deterministic chunk id, the best available heading, and the chunk text used for tool retrieval.
            """
        ),
        code_cell(
            """
            def _split_markdown_sections(markdown_text: str) -> list[dict]:
                sections: list[dict] = []
                current_heading = "Introduction"
                current_lines: list[str] = []

                for raw_line in markdown_text.splitlines():
                    line = raw_line.rstrip()
                    heading_match = HEADING_RE.match(line.strip())
                    if heading_match:
                        section_text = "\\n".join(current_lines).strip()
                        if section_text:
                            sections.append(
                                {"heading": current_heading, "text": section_text}
                            )
                        current_heading = heading_match.group(2).strip() or current_heading
                        current_lines = []
                        continue
                    current_lines.append(line)

                trailing_text = "\\n".join(current_lines).strip()
                if trailing_text:
                    sections.append({"heading": current_heading, "text": trailing_text})

                if not sections:
                    sections.append({"heading": "Introduction", "text": markdown_text.strip()})
                return sections


            def build_reading_chunks(markdown_text: str) -> list[dict]:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=int(CHUNK_SIZE),
                    chunk_overlap=int(CHUNK_OVERLAP),
                    separators=["\\n## ", "\\n### ", "\\n\\n", "\\n", " ", ""],
                )

                chunks: list[dict] = []
                for section_index, section in enumerate(_split_markdown_sections(markdown_text)):
                    heading = section["heading"]
                    section_text = section["text"].strip()
                    if not section_text:
                        continue
                    section_chunks = splitter.split_text(section_text)
                    for chunk_index, chunk_text in enumerate(section_chunks):
                        chunk_text = chunk_text.strip()
                        if not chunk_text:
                            continue
                        chunk_id = f"section-{section_index:03d}-chunk-{chunk_index:03d}"
                        chunks.append(
                            {
                                "chunk_id": chunk_id,
                                "section_index": section_index,
                                "chunk_index": chunk_index,
                                "heading": heading,
                                "text": chunk_text,
                                "preview": _compact_text(chunk_text, width=180),
                            }
                        )
                return chunks
            """
        ),
        code_cell(
            """
            CURRENT_READING_CHUNKS = []

            if not CURRENT_READING_MARKDOWN:
                print("Fetch a readable article first.")
            else:
                CURRENT_READING_CHUNKS = build_reading_chunks(CURRENT_READING_MARKDOWN)
                chunks_df = pd.DataFrame(CURRENT_READING_CHUNKS)
                print(f"Built {len(CURRENT_READING_CHUNKS)} reading chunks.")
                display(chunks_df[["chunk_id", "heading", "preview"]].head(20))
            """
        ),
        markdown_cell(
            """
            ## Thread Id And Notebook-Local Memory

            Notebook v1 keeps memory in-kernel only:

            - `MEMORY_BY_THREAD_ID` stores the LangChain message history
            - `SESSION_BY_THREAD_ID` stores the selected student/course/skill/reading bundle
            - `CHUNKS_BY_THREAD_ID` stores the extracted reading chunks

            **Production note**

            In production, the browser should persist the same deterministic thread id using a key like `reading-agent/thread/{thread_id}`.

            The future app should derive `student_id` from authenticated `/users/me`, then compose:

            - `thread_id = f"student-{student_id}:reading-{reading_id}"`

            The notebook intentionally uses in-memory state only for prototyping.
            """
        ),
        code_cell(
            """
            MEMORY_BY_THREAD_ID: dict[str, list[BaseMessage]] = {}
            SESSION_BY_THREAD_ID: dict[str, dict] = {}
            CHUNKS_BY_THREAD_ID: dict[str, list[dict]] = {}

            ACTIVE_THREAD_ID: str | None = None
            CURRENT_THREAD_ID: str | None = None
            READING_TUTOR_AGENT = None


            def build_thread_id(student_id: int, reading_id: str) -> str:
                return f"student-{student_id}:reading-{reading_id}"


            def initialize_reading_thread(bundle: dict, chunks: list[dict]) -> str:
                student_id = int(bundle["student"]["id"])
                reading_id = str(bundle["reading"]["id"])
                thread_id = build_thread_id(student_id, reading_id)
                SESSION_BY_THREAD_ID[thread_id] = bundle
                CHUNKS_BY_THREAD_ID[thread_id] = chunks
                MEMORY_BY_THREAD_ID.setdefault(thread_id, [])
                return thread_id
            """
        ),
        markdown_cell(
            """
            ## Retrieval And Tools

            The tutor never reads the whole article directly. It must call tools to access session context and the most relevant reading chunks.
            """
        ),
        code_cell(
            """
            def _tokenize(value: str) -> list[str]:
                return [
                    token
                    for token in TOKEN_RE.findall(str(value).lower())
                    if token and token not in STOPWORDS
                ]


            def _score_chunk(query: str, chunk: dict) -> float:
                query_tokens = _tokenize(query)
                if not query_tokens:
                    return 0.0

                chunk_token_counts = Counter(_tokenize(chunk["text"]))
                heading_tokens = set(_tokenize(chunk.get("heading", "")))

                overlap_score = sum(1.0 for token in set(query_tokens) if token in chunk_token_counts)
                frequency_score = sum(chunk_token_counts[token] for token in query_tokens) / max(
                    len(query_tokens), 1
                )
                heading_bonus = sum(0.75 for token in set(query_tokens) if token in heading_tokens)
                phrase_bonus = 1.5 if query.strip().lower() in chunk["text"].lower() else 0.0

                return overlap_score + frequency_score + heading_bonus + phrase_bonus


            def _search_chunks(thread_id: str, query: str, *, k: int = DEFAULT_CHUNK_SEARCH_K) -> list[dict]:
                chunks = CHUNKS_BY_THREAD_ID.get(thread_id, [])
                scored = []
                for chunk in chunks:
                    score = _score_chunk(query, chunk)
                    if score <= 0:
                        continue
                    scored.append(
                        {
                            "chunk_id": chunk["chunk_id"],
                            "heading": chunk["heading"],
                            "score": round(score, 3),
                            "preview": chunk["preview"],
                            "text": chunk["text"],
                        }
                    )

                if not scored:
                    fallback = []
                    for chunk in chunks[: max(1, int(k))]:
                        fallback.append(
                            {
                                "chunk_id": chunk["chunk_id"],
                                "heading": chunk["heading"],
                                "score": 0.0,
                                "preview": chunk["preview"],
                                "text": chunk["text"],
                            }
                        )
                    return fallback

                scored.sort(key=lambda item: (-item["score"], item["chunk_id"]))
                return scored[: max(1, int(k))]


            def _require_active_thread_id() -> str:
                if ACTIVE_THREAD_ID is None:
                    raise RuntimeError("No active reading thread is set.")
                return ACTIVE_THREAD_ID


            def _active_bundle() -> dict:
                thread_id = _require_active_thread_id()
                if thread_id not in SESSION_BY_THREAD_ID:
                    raise RuntimeError(f"Unknown reading thread: {thread_id}")
                return SESSION_BY_THREAD_ID[thread_id]


            @tool
            def get_session_context() -> str:
                \"\"\"Return the structured student, course, chapter, skill, and reading context.\"\"\"

                bundle = _active_bundle()
                payload = {
                    "student": bundle["student"],
                    "course": bundle["course"],
                    "chapter": bundle["chapter"],
                    "skill": {
                        "name": bundle["skill"]["name"],
                        "description": bundle["skill"]["description"],
                        "source": bundle["skill"]["source"],
                        "skill_type": bundle["skill"]["skill_type"],
                        "concepts": bundle["skill"]["concepts"],
                        "question_count": len(bundle["skill"]["questions"]),
                    },
                    "reading": {
                        "id": bundle["reading"]["id"],
                        "title": bundle["reading"]["title"],
                        "url": bundle["reading"]["url"],
                        "domain": bundle["reading"]["domain"],
                        "resource_type": bundle["reading"]["resource_type"],
                        "final_score": bundle["reading"]["final_score"],
                        "concepts_covered": bundle["reading"]["concepts_covered"],
                    },
                }
                return _json(payload)


            @tool
            def search_reading_chunks(query: str, k: int = DEFAULT_CHUNK_SEARCH_K) -> str:
                \"\"\"Search the extracted reading and return the most relevant grounded passages.\"\"\"

                thread_id = _require_active_thread_id()
                hits = _search_chunks(thread_id, query, k=max(1, min(int(k), 8)))
                return _json({"query": query, "hits": hits})


            @tool
            def get_skill_questions() -> str:
                \"\"\"Return the canonical easy, medium, and hard questions for the selected skill.\"\"\"

                bundle = _active_bundle()
                return _json(bundle["skill"]["questions"])
            """
        ),
        markdown_cell(
            """
            ## ReAct Tutor Prompt

            The prompt is rebuilt per turn from the active thread id so the tutor stays scoped to exactly one student and one reading.
            """
        ),
        code_cell(
            '''
            def _render_system_prompt(thread_id: str) -> str:
                bundle = SESSION_BY_THREAD_ID[thread_id]
                chunk_count = len(CHUNKS_BY_THREAD_ID.get(thread_id, []))

                student = bundle["student"]
                course = bundle["course"]
                chapter = bundle["chapter"]
                skill = bundle["skill"]
                reading = bundle["reading"]

                return f"""
                You are Lab Tutor's grounded reading tutor for one specific student and one specific reading.

                Session scope:
                - Thread ID: {thread_id}
                - Student: {student.get('first_name', '')} {student.get('last_name', '')} (id={student['id']}, email={student['email']})
                - Course: {course['title']} (id={course['id']})
                - Chapter: {chapter['title']} (index={chapter['chapter_index']})
                - Skill: {skill['name']} ({skill['skill_type']})
                - Reading: {reading['title']}
                - Extracted chunk count: {chunk_count}

                Your job:
                - help the student learn the selected reading
                - explain ideas clearly and concisely
                - summarize, quiz, and coach study strategy when useful
                - adapt your explanations to the student's course, chapter, and skill context

                Grounding rules:
                - Use only notebook-loaded session context and passages retrieved from tools.
                - Do not invent facts that are missing from the reading.
                - If the reading does not contain enough evidence, say that clearly.
                - Prefer short explanations and targeted follow-up questions.
                - Cite grounded evidence by referring to passage headings or quoted wording from retrieved chunks.

                Available tools:
                - get_session_context(): load structured student / course / chapter / skill / reading context
                - search_reading_chunks(query, k=4): fetch the most relevant reading passages
                - get_skill_questions(): retrieve the canonical course questions for this skill

                Behavioral style:
                - warm, encouraging, and efficient
                - never overwhelm the student
                - when quizzing, ask one focused question at a time unless the student asks for more
                - when summarizing, highlight the key takeaways and what to pay attention to next
                """.strip()


            def build_reading_tutor_prompt(state: dict) -> list[BaseMessage]:
                thread_id = _require_active_thread_id()
                messages = list(state.get("messages", []))
                if len(messages) > int(PROMPT_MESSAGE_WINDOW):
                    messages = messages[-int(PROMPT_MESSAGE_WINDOW) :]
                return [SystemMessage(content=_render_system_prompt(thread_id)), *messages]
            '''
        ),
        markdown_cell(
            """
            ## Agent Construction

            This creates one single-agent ReAct tutor backed by the repo's configured LLM settings.
            """
        ),
        code_cell(
            """
            def create_reading_tutor_agent():
                llm = create_llm()
                return create_react_agent(
                    llm,
                    tools=[get_session_context, search_reading_chunks, get_skill_questions],
                    prompt=build_reading_tutor_prompt,
                    name="reading_react_tutor",
                )


            READING_TUTOR_AGENT = create_reading_tutor_agent()
            print("Reading ReAct tutor agent ready.")
            """
        ),
        markdown_cell(
            """
            ## Initialize The Current Thread

            This step binds the loaded session bundle and extracted chunks to the deterministic thread id.
            """
        ),
        code_cell(
            """
            CURRENT_THREAD_ID = None

            if CURRENT_SESSION_BUNDLE is None:
                print("Load a session bundle first.")
            elif not CURRENT_READING_CHUNKS:
                print("Fetch and chunk the reading first.")
            else:
                CURRENT_THREAD_ID = initialize_reading_thread(
                    CURRENT_SESSION_BUNDLE,
                    CURRENT_READING_CHUNKS,
                )
                print(f"Initialized reading thread: {CURRENT_THREAD_ID}")
            """
        ),
        markdown_cell(
            """
            ## Chat With The Tutor

            Edit `USER_MESSAGE`, re-run the next cell, and continue the conversation on the same thread id.
            """
        ),
        code_cell(
            """
            def _extract_ai_text(message: AIMessage) -> str:
                content = message.content
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(str(item.get("text", "")))
                    return "\\n".join(part for part in parts if part).strip()
                return str(content).strip()


            def run_tutor_turn(thread_id: str, user_message: str) -> dict:
                if not user_message or not user_message.strip():
                    raise ValueError("user_message must not be empty.")
                if thread_id not in SESSION_BY_THREAD_ID:
                    raise ValueError(f"Unknown thread_id: {thread_id}")
                if READING_TUTOR_AGENT is None:
                    raise RuntimeError("READING_TUTOR_AGENT has not been created yet.")

                prior_messages = list(MEMORY_BY_THREAD_ID.get(thread_id, []))
                next_messages = [*prior_messages, HumanMessage(content=user_message.strip())]

                global ACTIVE_THREAD_ID
                previous_thread_id = ACTIVE_THREAD_ID
                ACTIVE_THREAD_ID = thread_id
                try:
                    result = READING_TUTOR_AGENT.invoke({"messages": next_messages})
                finally:
                    ACTIVE_THREAD_ID = previous_thread_id

                updated_messages = list(result["messages"])
                MEMORY_BY_THREAD_ID[thread_id] = updated_messages

                final_ai_message = next(
                    message
                    for message in reversed(updated_messages)
                    if isinstance(message, AIMessage)
                )
                response_text = _extract_ai_text(final_ai_message)

                return {
                    "thread_id": thread_id,
                    "response_text": response_text,
                    "messages": updated_messages,
                    "message_count": len(updated_messages),
                }


            def reset_thread_memory(thread_id: str) -> None:
                MEMORY_BY_THREAD_ID[thread_id] = []
            """
        ),
        code_cell(
            """
            LAST_TUTOR_RESULT = None

            if CURRENT_THREAD_ID is None:
                print("Initialize the current reading thread first.")
            else:
                LAST_TUTOR_RESULT = run_tutor_turn(CURRENT_THREAD_ID, USER_MESSAGE)
                display(Markdown(LAST_TUTOR_RESULT["response_text"]))
            """
        ),
        markdown_cell(
            """
            ## Debug Helpers

            These cells help inspect the loaded context, the extracted article, chunk retrieval behavior, and notebook-local memory.
            """
        ),
        code_cell(
            """
            if CURRENT_SESSION_BUNDLE is None:
                print("No session bundle is loaded.")
            else:
                debug_context = {
                    "student": CURRENT_SESSION_BUNDLE["student"],
                    "course": CURRENT_SESSION_BUNDLE["course"],
                    "chapter": CURRENT_SESSION_BUNDLE["chapter"],
                    "skill": {
                        "name": CURRENT_SESSION_BUNDLE["skill"]["name"],
                        "description": CURRENT_SESSION_BUNDLE["skill"]["description"],
                        "concepts": CURRENT_SESSION_BUNDLE["skill"]["concepts"],
                        "questions": CURRENT_SESSION_BUNDLE["skill"]["questions"],
                    },
                    "reading": {
                        "id": CURRENT_SESSION_BUNDLE["reading"]["id"],
                        "title": CURRENT_SESSION_BUNDLE["reading"]["title"],
                        "url": CURRENT_SESSION_BUNDLE["reading"]["url"],
                        "resource_type": CURRENT_SESSION_BUNDLE["reading"]["resource_type"],
                        "final_score": CURRENT_SESSION_BUNDLE["reading"]["final_score"],
                        "concepts_covered": CURRENT_SESSION_BUNDLE["reading"]["concepts_covered"],
                    },
                }
                display(Markdown(f"```json\\n{_json(debug_context)}\\n```"))
            """
        ),
        code_cell(
            """
            if not CURRENT_READING_MARKDOWN:
                print("No reading markdown is loaded.")
            else:
                preview = CURRENT_READING_MARKDOWN[:4000]
                display(Markdown(preview))
            """
        ),
        code_cell(
            """
            if CURRENT_THREAD_ID is None:
                print("Initialize the current reading thread first.")
            else:
                debug_hits = _search_chunks(CURRENT_THREAD_ID, DEBUG_QUERY, k=3)
                display(Markdown(f"```json\\n{_json(debug_hits)}\\n```"))
            """
        ),
        code_cell(
            """
            def preview_thread_memory(thread_id: str) -> pd.DataFrame:
                messages = MEMORY_BY_THREAD_ID.get(thread_id, [])
                rows = []
                for index, message in enumerate(messages):
                    role = getattr(message, "type", type(message).__name__)
                    content = getattr(message, "content", "")
                    if isinstance(content, list):
                        rendered = json.dumps(content, ensure_ascii=False)
                    else:
                        rendered = str(content)
                    rows.append(
                        {
                            "index": index,
                            "message_type": type(message).__name__,
                            "role": role,
                            "preview": _compact_text(rendered, width=220),
                        }
                    )
                return pd.DataFrame(rows)


            if CURRENT_THREAD_ID is None:
                print("Initialize the current reading thread first.")
            else:
                display(preview_thread_memory(CURRENT_THREAD_ID))
            """
        ),
        code_cell(
            """
            NEO4J_DRIVER.close()
            print("Neo4j driver closed.")
            """
        ),
    ]

    notebook = nbf.v4.new_notebook()
    notebook["cells"] = cells
    notebook["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
    }
    return notebook


def main() -> None:
    notebook_dir = Path(__file__).resolve().parent
    notebook_path = notebook_dir / NOTEBOOK_FILENAME
    notebook = build_notebook()
    nbf.write(notebook, notebook_path)
    print(notebook_path)


if __name__ == "__main__":
    main()
