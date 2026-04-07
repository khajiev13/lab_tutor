from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf

NOTEBOOK_FILENAME = "resource_answerability_llm_judge.ipynb"


def markdown_cell(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(dedent(source).strip() + "\n")


def code_cell(source: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(dedent(source).strip() + "\n")


def build_notebook() -> nbf.NotebookNode:
    cells: list[nbf.NotebookNode] = [
        markdown_cell(
            """
            # Resource Answerability Evaluation With a Yes/No LLM Judge

            This notebook evaluates whether the readings and videos retrieved for a student's visible learning-path skills contain enough information for a strict LLM judge to say a question is answerable using only the provided evidence.

            It is designed for the conference-paper experiment where we want to test retrieval quality indirectly through evidence-grounded yes/no classification:

            - `Readings-only`: are the retrieved readings enough to answer the question?
            - `Videos-only`: are the retrieved videos enough to answer the question?
            - `Combined`: are the top readings and videos together enough to answer the question?
            """
        ),
        markdown_cell(
            """
            ## Experiment Design

            **Research question**

            Can the resources retrieved by Lab Tutor's reading and video agents answer skill-grounded questions without using outside knowledge?

            **Protocol**

            1. Load a student's visible course-path skills for a target course from Neo4j.
            2. Confirm that each selected skill has questions, readings, and videos.
            3. Fetch evidence from the reading URLs and video transcripts when available.
            4. Ask a strict LLM judge whether each question is answerable using only the provided evidence.
            5. Record a binary `YES/NO` answerability judgment, evidence quotes, and missing-information explanations.
            6. Aggregate results by modality, skill type, and question difficulty.

            **Judge policy**

            - The judge must use only the provided evidence.
            - The judge does not use outside knowledge or guess.
            - If the evidence is insufficient, the judge must return `NO` and explain what is missing.
            - The notebook preserves raw per-question judgments so the paper can include summary metrics, worked examples, and failure analysis.
            """
        ),
        markdown_cell(
            """
            ## Professional Use Notes

            To keep this experiment publication-ready:

            - Use a deterministic judge setup with `temperature=0`.
            - Treat this as a resource answerability audit, not a gold-answer verification task.
            - Save raw artifacts for auditability.
            - Inspect coverage failures before running the expensive judge pass.
            - Manually review a stratified sample of judged items before reporting final paper numbers.

            This notebook supports local overrides for both Neo4j and the LLM endpoint, so you can run it against your localhost graph even if the repo `.env` is incomplete.
            """
        ),
        code_cell(
            """
            from __future__ import annotations

            import html
            import sys
            import time
            from collections import deque
            from copy import deepcopy
            from pathlib import Path

            import ipywidgets as widgets
            import pandas as pd
            import plotly.express as px
            from IPython.display import Markdown, display

            NOTEBOOK_DIR = None
            cwd = Path.cwd().resolve()
            search_roots = [cwd, *cwd.parents]
            for root in search_roots:
                direct_helper = root / "resource_answerability_eval_utils.py"
                repo_helper = (
                    root
                    / "backend"
                    / "app"
                    / "modules"
                    / "student_learning_path"
                    / "notebooks"
                    / "resource_answerability_eval_utils.py"
                )
                if direct_helper.exists():
                    NOTEBOOK_DIR = root
                    break
                if repo_helper.exists():
                    NOTEBOOK_DIR = repo_helper.parent
                    break

            if NOTEBOOK_DIR is None:
                raise RuntimeError("Could not locate the student learning path notebook directory.")

            REPO_ROOT = None
            for candidate in [NOTEBOOK_DIR, *NOTEBOOK_DIR.parents]:
                if (candidate / "backend").exists() and (candidate / "frontend").exists():
                    REPO_ROOT = candidate
                    break

            if REPO_ROOT is None:
                raise RuntimeError("Could not locate the Lab Tutor repo root.")

            for path in [NOTEBOOK_DIR, REPO_ROOT / "backend"]:
                path_text = str(path)
                if path_text not in sys.path:
                    sys.path.insert(0, path_text)

            import resource_answerability_eval_utils as eval_utils

            pd.set_option("display.max_colwidth", 200)
            pd.set_option("display.max_rows", 200)

            print(f"Repo root: {REPO_ROOT}")
            print(f"Notebook dir: {NOTEBOOK_DIR}")
            """
        ),
        markdown_cell(
            """
            ## Configuration

            Fill in the identifiers below. The connection fields can stay `None` if your local `backend/.env` already contains the right values.

            By default, the notebook evaluates only the skills that appear in the student's mapped course path. Set `INCLUDE_ORPHAN_SELECTED_SKILLS = True` only if you explicitly want to audit selected skills that do not appear in the visible learning path.

            Recommended workflow:

            1. Run the course-discovery cell.
            2. Set `COURSE_ID`.
            3. Run the student-discovery cell.
            4. Set either `STUDENT_ID` or `STUDENT_EMAIL`.
            5. Keep `LIMIT_SKILLS` and `QUESTION_LIMIT_PER_SKILL` small for a pilot run, then remove the limits for the paper run.
            6. Increase `HYDRATION_MAX_WORKERS` and `JUDGE_MAX_WORKERS` if you want faster runs, or set them to `1` to force sequential execution for debugging.
            """
        ),
        code_cell(
            """
            COURSE_ID = None
            STUDENT_ID = None
            STUDENT_EMAIL = None

            LIMIT_SKILLS = None
            QUESTION_LIMIT_PER_SKILL = None
            SKILL_NAME_ALLOWLIST = None
            INCLUDE_ORPHAN_SELECTED_SKILLS = False

            READING_TIMEOUT_SECONDS = 20
            VIDEO_TIMEOUT_SECONDS = 20
            HYDRATION_MAX_WORKERS = 8
            JUDGE_MAX_WORKERS = 4
            MODALITIES = ("readings", "videos", "combined")
            ARTIFACT_PREFIX = "resource_answerability"

            NEO4J_URI = None
            NEO4J_USERNAME = None
            NEO4J_PASSWORD = None
            NEO4J_DATABASE = None

            LLM_API_KEY = None
            LLM_BASE_URL = None
            LLM_MODEL = None
            BACKFILL_MISSING_QUESTIONS = False

            PLOT_FONT_FAMILY = "Times New Roman, Times, serif"
            PLOT_BASE_FONT_SIZE = 18
            PLOT_TITLE_FONT_SIZE = 24
            PLOT_AXIS_TITLE_FONT_SIZE = 20
            PLOT_TICK_FONT_SIZE = 18
            PLOT_LEGEND_FONT_SIZE = 17
            PLOT_TEXT_FONT_SIZE = 16
            PLOT_WIDTH = 1150
            PLOT_HEIGHT = 700
            PROGRESS_RECENT_LIMIT = 8
            """
        ),
        code_cell(
            """
            def style_publication_figure(fig):
                fig.update_layout(
                    template="plotly_white",
                    width=PLOT_WIDTH,
                    height=PLOT_HEIGHT,
                    font={
                        "family": PLOT_FONT_FAMILY,
                        "size": PLOT_BASE_FONT_SIZE,
                        "color": "black",
                    },
                    title={
                        "font": {
                            "family": PLOT_FONT_FAMILY,
                            "size": PLOT_TITLE_FONT_SIZE,
                            "color": "black",
                        },
                        "x": 0.5,
                        "xanchor": "center",
                    },
                    legend={
                        "orientation": "h",
                        "yanchor": "bottom",
                        "y": 1.02,
                        "xanchor": "center",
                        "x": 0.5,
                        "font": {
                            "family": PLOT_FONT_FAMILY,
                            "size": PLOT_LEGEND_FONT_SIZE,
                        },
                        "title": {
                            "font": {
                                "family": PLOT_FONT_FAMILY,
                                "size": PLOT_LEGEND_FONT_SIZE,
                            }
                        },
                    },
                    xaxis={
                        "title": {
                            "font": {
                                "family": PLOT_FONT_FAMILY,
                                "size": PLOT_AXIS_TITLE_FONT_SIZE,
                            }
                        },
                        "tickfont": {
                            "family": PLOT_FONT_FAMILY,
                            "size": PLOT_TICK_FONT_SIZE,
                        },
                        "automargin": True,
                    },
                    yaxis={
                        "title": {
                            "font": {
                                "family": PLOT_FONT_FAMILY,
                                "size": PLOT_AXIS_TITLE_FONT_SIZE,
                            }
                        },
                        "tickfont": {
                            "family": PLOT_FONT_FAMILY,
                            "size": PLOT_TICK_FONT_SIZE,
                        },
                        "tickformat": ".0%",
                        "range": [0, 1.12],
                        "automargin": True,
                    },
                    margin={"l": 90, "r": 40, "t": 120, "b": 80},
                    uniformtext_minsize=PLOT_TEXT_FONT_SIZE,
                    uniformtext_mode="show",
                    bargap=0.22,
                )
                fig.update_traces(
                    texttemplate="%{text:.1%}",
                    textposition="outside",
                    textfont={
                        "family": PLOT_FONT_FAMILY,
                        "size": PLOT_TEXT_FONT_SIZE,
                        "color": "black",
                    },
                    cliponaxis=False,
                )
                return fig
            """
        ),
        code_cell(
            """
            class NotebookProgressTracker:
                def __init__(self, *, title: str, total: int, recent_limit: int = PROGRESS_RECENT_LIMIT):
                    self.total = max(int(total), 1)
                    self.recent_events = deque(maxlen=recent_limit)

                    self.title_widget = widgets.HTML(
                        value=(
                            "<div style='font-size:18px; font-weight:600; margin-bottom:8px;'>"
                            f"{html.escape(title)}"
                            "</div>"
                        )
                    )
                    self.progress_widget = widgets.IntProgress(
                        value=0,
                        min=0,
                        max=self.total,
                        bar_style="info",
                        layout=widgets.Layout(width="100%"),
                    )
                    self.counter_widget = widgets.HTML()
                    self.status_widget = widgets.HTML()
                    self.recent_widget = widgets.HTML()
                    self.container = widgets.VBox(
                        [
                            self.title_widget,
                            self.progress_widget,
                            self.counter_widget,
                            self.status_widget,
                            self.recent_widget,
                        ]
                    )
                    display(self.container)
                    self._render(status_text="Waiting to start...")

                def _render(
                    self,
                    *,
                    status_text: str,
                    details_text: str | None = None,
                    bar_style: str = "info",
                ) -> None:
                    self.progress_widget.bar_style = bar_style
                    completed = min(self.progress_widget.value, self.progress_widget.max)
                    self.counter_widget.value = (
                        "<div style='margin-top:6px; font-size:14px;'>"
                        f"<b>Progress:</b> {completed}/{self.progress_widget.max}"
                        "</div>"
                    )
                    self.status_widget.value = (
                        "<div style='margin-top:6px; font-size:14px;'>"
                        f"<b>Current:</b> {html.escape(status_text)}"
                        "</div>"
                    )
                    if details_text:
                        self.recent_events.appendleft(details_text)
                    if self.recent_events:
                        items = "".join(
                            f"<li>{html.escape(item)}</li>" for item in self.recent_events
                        )
                        self.recent_widget.value = (
                            "<div style='margin-top:8px; font-size:13px;'>"
                            "<b>Recent events</b>"
                            f"<ul style='margin-top:6px;'>{items}</ul>"
                            "</div>"
                        )
                    else:
                        self.recent_widget.value = ""

                def callback(self, event: dict[str, object]) -> None:
                    total = max(int(event.get("total", self.total) or self.total), 1)
                    if total != self.progress_widget.max:
                        self.progress_widget.max = total

                    completed = min(int(event.get("completed", 0) or 0), total)
                    self.progress_widget.value = completed

                    phase = str(event.get("phase", "work")).title()
                    message = str(event.get("message", "Working..."))
                    stage = str(event.get("stage", ""))

                    detail_parts = []
                    for label, key in [
                        ("Skill", "skill_name"),
                        ("Resource", "resource_kind"),
                        ("Title", "resource_title"),
                        ("Question", "question_id"),
                        ("Modality", "modality"),
                        ("Status", "fetch_status"),
                    ]:
                        value = event.get(key)
                        if value not in (None, ""):
                            detail_parts.append(f"{label}: {value}")

                    details_text = " | ".join(detail_parts) if detail_parts else message
                    if stage in {"complete"}:
                        bar_style = "success"
                    elif stage.endswith("error"):
                        bar_style = "danger"
                    else:
                        bar_style = "info"
                    self._render(
                        status_text=f"{phase}: {message}",
                        details_text=details_text,
                        bar_style=bar_style,
                    )

                def complete(self, message: str) -> None:
                    self.progress_widget.value = self.progress_widget.max
                    self._render(
                        status_text=message,
                        details_text=message,
                        bar_style="success",
                    )

            def apply_bundle_filters(raw_bundle):
                bundle = deepcopy(raw_bundle)

                if SKILL_NAME_ALLOWLIST:
                    allowlist = {name.strip() for name in SKILL_NAME_ALLOWLIST}
                    bundle["skills"] = [
                        skill for skill in bundle["skills"] if skill.get("name") in allowlist
                    ]

                if LIMIT_SKILLS is not None:
                    bundle["skills"] = bundle["skills"][: int(LIMIT_SKILLS)]

                if QUESTION_LIMIT_PER_SKILL is not None:
                    for skill in bundle["skills"]:
                        skill["questions"] = skill.get("questions", [])[: int(QUESTION_LIMIT_PER_SKILL)]

                bundle["skill_count"] = len(bundle["skills"])
                bundle["evaluation_config"] = {
                    "course_id": COURSE_ID,
                    "student_id": STUDENT_ID,
                    "student_email": STUDENT_EMAIL,
                    "limit_skills": LIMIT_SKILLS,
                    "question_limit_per_skill": QUESTION_LIMIT_PER_SKILL,
                    "skill_name_allowlist": SKILL_NAME_ALLOWLIST,
                    "include_orphan_selected_skills": INCLUDE_ORPHAN_SELECTED_SKILLS,
                    "modalities": list(MODALITIES),
                    "hydration_max_workers": HYDRATION_MAX_WORKERS,
                    "judge_max_workers": JUDGE_MAX_WORKERS,
                    "backfill_missing_questions": BACKFILL_MISSING_QUESTIONS,
                }
                return bundle
            """
        ),
        code_cell(
            """
            driver = eval_utils.create_neo4j_driver(
                repo_root=REPO_ROOT,
                neo4j_uri=NEO4J_URI,
                neo4j_username=NEO4J_USERNAME,
                neo4j_password=NEO4J_PASSWORD,
            )
            neo4j_database = eval_utils.get_neo4j_database(
                repo_root=REPO_ROOT,
                neo4j_database=NEO4J_DATABASE,
            )

            print(f"Neo4j database: {neo4j_database}")
            """
        ),
        markdown_cell(
            """
            ## Course Discovery

            Use this table to find the course you want to evaluate. If you already know the course id, you can skip ahead.
            """
        ),
        code_cell(
            """
            courses_df = pd.DataFrame(
                eval_utils.list_courses(driver, database=neo4j_database, limit=50)
            )
            if courses_df.empty:
                print("No CLASS nodes were found in Neo4j.")
            else:
                display(courses_df)
            """
        ),
        code_cell(
            """
            if COURSE_ID is None and len(courses_df) == 1:
                COURSE_ID = int(courses_df.iloc[0]["course_id"])
                print(f"Auto-selected the only course in Neo4j: COURSE_ID={COURSE_ID}")
            elif COURSE_ID is not None:
                print(f"Using manually configured COURSE_ID={COURSE_ID}")
            else:
                print("Multiple courses detected. Set COURSE_ID manually in the configuration cell.")
            """
        ),
        markdown_cell(
            """
            ## Student Discovery

            This lists students with selected skills. If `COURSE_ID` is set, the list is anchored to students enrolled in that course.
            """
        ),
        code_cell(
            """
            students_df = pd.DataFrame(
                eval_utils.list_students_with_selected_skills(
                    driver,
                    database=neo4j_database,
                    course_id=COURSE_ID,
                    limit=50,
                    only_course_path_skills=not INCLUDE_ORPHAN_SELECTED_SKILLS,
                )
            )
            if students_df.empty:
                print("No students with selected skills were found for the current filter.")
            else:
                display(students_df)
            """
        ),
        code_cell(
            """
            if STUDENT_ID is None and not STUDENT_EMAIL and len(students_df) == 1:
                row = students_df.iloc[0]
                STUDENT_ID = int(row["student_id"])
                if row.get("email"):
                    STUDENT_EMAIL = str(row["email"])
                print(
                    "Auto-selected the only student with selected skills: "
                    f"STUDENT_ID={STUDENT_ID}, STUDENT_EMAIL={STUDENT_EMAIL}"
                )
            elif STUDENT_ID is not None or STUDENT_EMAIL:
                print(
                    "Using manually configured student selector: "
                    f"STUDENT_ID={STUDENT_ID}, STUDENT_EMAIL={STUDENT_EMAIL}"
                )
            else:
                print(
                    "Multiple eligible students detected. "
                    "Set STUDENT_ID or STUDENT_EMAIL manually in the configuration cell."
                )
            """
        ),
        markdown_cell(
            """
            ## Load the Selected-Skill Bundle

            This cell loads the student, their visible learning-path skills, the generated questions, and the attached reading/video resources. Optional skill and question limits are applied after loading so you can do a cheap pilot before the full run.
            """
        ),
        code_cell(
            """
            if COURSE_ID is None:
                raise ValueError("Set COURSE_ID before loading the experiment bundle.")
            if STUDENT_ID is None and not STUDENT_EMAIL:
                raise ValueError("Set either STUDENT_ID or STUDENT_EMAIL before loading the bundle.")

            raw_bundle = eval_utils.load_selected_skill_bundle(
                driver,
                database=neo4j_database,
                course_id=COURSE_ID,
                student_id=STUDENT_ID,
                student_email=STUDENT_EMAIL,
                only_course_path_skills=not INCLUDE_ORPHAN_SELECTED_SKILLS,
            )

            bundle = apply_bundle_filters(raw_bundle)

            print(
                f"Loaded {bundle['skill_count']} skills for student "
                f"{bundle['student'].get('email') or bundle['student'].get('id')}"
            )
            """
        ),
        code_cell(
            """
            coverage_df = pd.DataFrame(eval_utils.summarize_bundle(bundle))
            if coverage_df.empty:
                print("No skills are available after the current filters.")
                coverage_issues_df = pd.DataFrame()
                coverage_by_type_df = pd.DataFrame()
            else:
                coverage_df = coverage_df.sort_values(
                    ["chapter_index", "skill_type", "skill_name"],
                    na_position="last",
                )
                display(coverage_df)

                coverage_issues_df = coverage_df[
                    (coverage_df["question_count"] == 0)
                    | (coverage_df["reading_count"] == 0)
                    | (coverage_df["video_count"] == 0)
                ].copy()

                print("Coverage issues:")
                if coverage_issues_df.empty:
                    print("None. All loaded skills have at least one question, reading, and video.")
                else:
                    display(coverage_issues_df)

                coverage_by_type_df = (
                    coverage_df.groupby("skill_type", dropna=False)
                    .agg(
                        skills=("skill_name", "count"),
                        questions=("question_count", "sum"),
                        readings=("reading_count", "sum"),
                        videos=("video_count", "sum"),
                    )
                    .reset_index()
                )
                display(coverage_by_type_df)
            """
        ),
        markdown_cell(
            """
            ## Optional Question Backfill

            If the loaded bundle has missing question sets, you can use this step to generate and write them directly from the notebook before continuing with the yes/no answerability evaluation.
            """
        ),
        code_cell(
            """
            missing_question_skill_names = [
                skill["name"] for skill in bundle["skills"] if not skill.get("questions", [])
            ]
            print(f"Skills missing questions: {len(missing_question_skill_names)}")
            if missing_question_skill_names:
                display(pd.DataFrame({"skill_name": missing_question_skill_names}))
                print(
                    "Set BACKFILL_MISSING_QUESTIONS = True in the configuration cell and rerun "
                    "the next cell to generate missing question sets."
                )
            else:
                print("No missing question sets detected.")
            """
        ),
        code_cell(
            """
            backfill_result = {
                "bundle": bundle,
                "generated_skills": [],
                "failed_skills": [],
            }

            if BACKFILL_MISSING_QUESTIONS and missing_question_skill_names:
                question_backfill_tracker = NotebookProgressTracker(
                    title="Backfilling missing question sets",
                    total=len(missing_question_skill_names),
                )
                backfill_start_time = time.time()
                backfill_result = eval_utils.backfill_missing_questions(
                    driver,
                    database=neo4j_database,
                    bundle=bundle,
                    progress_callback=question_backfill_tracker.callback,
                )
                backfill_elapsed = time.time() - backfill_start_time
                question_backfill_tracker.complete(
                    f"Question backfill completed in {backfill_elapsed:.1f}s"
                )

                raw_bundle = eval_utils.load_selected_skill_bundle(
                    driver,
                    database=neo4j_database,
                    course_id=COURSE_ID,
                    student_id=STUDENT_ID,
                    student_email=STUDENT_EMAIL,
                    only_course_path_skills=not INCLUDE_ORPHAN_SELECTED_SKILLS,
                )
                bundle = apply_bundle_filters(raw_bundle)
                coverage_df = pd.DataFrame(eval_utils.summarize_bundle(bundle))
                if not coverage_df.empty:
                    coverage_df = coverage_df.sort_values(
                        ["chapter_index", "skill_type", "skill_name"],
                        na_position="last",
                    )

                print(
                    f"Question backfill completed in {backfill_elapsed:.1f}s: "
                    f"{len(backfill_result['generated_skills'])} generated, "
                    f"{len(backfill_result['failed_skills'])} failed"
                )
                if backfill_result["failed_skills"]:
                    display(pd.DataFrame(backfill_result["failed_skills"]))
            elif BACKFILL_MISSING_QUESTIONS:
                print("No missing questions to backfill.")
            """
        ),
        markdown_cell(
            """
            ## Hydrate Evidence

            The experiment uses the actual resource content whenever possible:

            - readings: fetch page HTML and extract readable text
            - videos: fetch YouTube captions when available, otherwise fall back to stored search metadata

            This step can take a while if many resources need to be fetched, so it now hydrates resources in parallel. A live loader below shows the current item, total progress, and the most recent fetch events.
            """
        ),
        code_cell(
            """
            resource_total = sum(
                len(skill.get("readings", [])) + len(skill.get("videos", []))
                for skill in bundle["skills"]
            )
            hydration_tracker = NotebookProgressTracker(
                title=f"Hydrating readings and videos ({HYDRATION_MAX_WORKERS} workers)",
                total=resource_total,
            )
            start_time = time.time()
            hydrated_bundle = eval_utils.materialize_bundle_evidence(
                bundle,
                reading_timeout_seconds=READING_TIMEOUT_SECONDS,
                video_timeout_seconds=VIDEO_TIMEOUT_SECONDS,
                max_workers=HYDRATION_MAX_WORKERS,
                progress_callback=hydration_tracker.callback,
            )
            elapsed = time.time() - start_time
            hydration_tracker.complete(f"Evidence hydration completed in {elapsed:.1f}s")
            print(f"Evidence hydration completed in {elapsed:.1f}s")
            """
        ),
        code_cell(
            """
            evidence_rows = []
            for skill in hydrated_bundle["skills"]:
                for reading in skill.get("readings", []):
                    evidence = reading.get("evidence", {})
                    evidence_rows.append(
                        {
                            "skill_name": skill.get("name", ""),
                            "skill_type": skill.get("skill_type", ""),
                            "resource_group": "reading",
                            "title": reading.get("title", ""),
                            "url": reading.get("url", ""),
                            "fetch_status": evidence.get("fetch_status", ""),
                            "content_source": evidence.get("content_source", ""),
                            "content_chars": len(evidence.get("content_text", "")),
                        }
                    )
                for video in skill.get("videos", []):
                    evidence = video.get("evidence", {})
                    evidence_rows.append(
                        {
                            "skill_name": skill.get("name", ""),
                            "skill_type": skill.get("skill_type", ""),
                            "resource_group": "video",
                            "title": video.get("title", ""),
                            "url": video.get("url", ""),
                            "fetch_status": evidence.get("fetch_status", ""),
                            "content_source": evidence.get("content_source", ""),
                            "content_chars": len(evidence.get("content_text", "")),
                        }
                    )

            evidence_df = pd.DataFrame(evidence_rows)
            display(evidence_df.head(20))

            if not evidence_df.empty:
                evidence_status_df = (
                    evidence_df.groupby(
                        ["resource_group", "fetch_status", "content_source"], dropna=False
                    )
                    .size()
                    .reset_index(name="count")
                    .sort_values(["resource_group", "count"], ascending=[True, False])
                )
                display(evidence_status_df)
            """
        ),
        markdown_cell(
            """
            ## Optional Preview Before the Judge Run

            Use this cell to inspect the evidence block for one skill and one modality before you launch the full experiment.
            """
        ),
        code_cell(
            """
            PREVIEW_SKILL_INDEX = 0
            PREVIEW_QUESTION_INDEX = 0
            PREVIEW_MODALITY = "combined"

            if not hydrated_bundle["skills"]:
                raise ValueError("The hydrated bundle is empty. Adjust the skill filters and rerun.")

            preview_skill = hydrated_bundle["skills"][PREVIEW_SKILL_INDEX]
            preview_evidence_text, preview_resources = eval_utils.build_modality_evidence(
                preview_skill,
                PREVIEW_MODALITY,
            )

            if not preview_skill.get("questions"):
                display(
                    Markdown(
                        f"### Preview unavailable\\n"
                        f"**Skill:** {preview_skill['name']}  \\n"
                        "This skill does not currently have generated questions. "
                        "Run the optional question backfill step or rerun Build My Learning Path."
                    )
                )
            else:
                preview_question = preview_skill["questions"][PREVIEW_QUESTION_INDEX]
                display(
                    Markdown(
                        f"### Preview\\n"
                        f"**Skill:** {preview_skill['name']}  \\n"
                        f"**Question:** {preview_question['text']}  \\n"
                        f"**Modality:** {PREVIEW_MODALITY}"
                    )
                )
            display(pd.DataFrame(preview_resources)[["title", "url", "resource_type", "final_score"]])
            print(preview_evidence_text[:5000])
            """
        ),
        markdown_cell(
            """
            ## Judge Input Audit

            This cell verifies that the judge will actually receive hydrated reading/video content rather than only titles or URLs. It shows the number of resources passed to the judge, the total evidence length, and a preview of the evidence text that will be inserted into the prompt.
            """
        ),
        code_cell(
            """
            JUDGE_INPUT_AUDIT_LIMIT = 12

            judge_input_audit_rows = []
            for skill in hydrated_bundle["skills"]:
                for modality in MODALITIES:
                    evidence_text, used_resources = eval_utils.build_modality_evidence(skill, modality)
                    judge_input_audit_rows.append(
                        {
                            "skill_name": skill.get("name", ""),
                            "difficulty_mix": ", ".join(
                                question.get("difficulty", "")
                                for question in skill.get("questions", [])
                            ),
                            "modality": modality,
                            "used_resource_count": len(used_resources),
                            "evidence_chars": len(evidence_text),
                            "has_nonempty_evidence": bool(evidence_text.strip()),
                            "resource_titles": [resource.get("title", "") for resource in used_resources],
                            "evidence_preview": evidence_text[:500],
                        }
                    )

            judge_input_audit_df = pd.DataFrame(judge_input_audit_rows)
            if judge_input_audit_df.empty:
                print("No judge inputs are available yet.")
            else:
                display(judge_input_audit_df.head(JUDGE_INPUT_AUDIT_LIMIT))
                print(
                    "Rows above confirm the exact evidence payload shape that will be inserted "
                    "into the LLM judge prompt."
                )
            """
        ),
        markdown_cell(
            """
            ## Metric Definitions

            - `Answerable = YES`: the evidence contains enough information for a student to answer the question correctly.
            - `Answerable = NO`: the evidence does not contain enough information, and the judge explains what is missing.
            - `Answerable Rate`: the percentage of judged question-resource pairs marked `YES`.

            This notebook uses one main evaluation signal: binary answerability. The judge also returns evidence quotes, evidence strength, confidence, and a missing-information explanation for `NO` cases.
            """
        ),
        markdown_cell(
            """
            ## Judge Setup

            The judge client is created only here so that you can do the Neo4j discovery and evidence checks without spending any model calls.
            """
        ),
        code_cell(
            """
            judge_client, default_judge_model = eval_utils.create_llm_client(
                repo_root=REPO_ROOT,
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
            )
            judge_model = LLM_MODEL or default_judge_model

            print(f"Judge model: {judge_model}")
            """
        ),
        markdown_cell(
            """
            ## Run the Blind LLM-as-Judge Experiment

            Each question is evaluated independently for each requested modality. The judge sees the skill, the question, the answer options, and the modality-specific evidence, and returns a strict `YES/NO` answerability decision with supporting evidence or a missing-information explanation. The notebook can judge multiple question-modality pairs in parallel, and the loader shows which skill/question/modality is being processed so you can see that the experiment is actively progressing.
            """
        ),
        code_cell(
            """
            judge_total = sum(
                len(skill.get("questions", [])) * len(MODALITIES)
                for skill in hydrated_bundle["skills"]
            )
            result_rows = []
            judge_elapsed = 0.0

            if judge_total == 0:
                print(
                    "No questions are available for judging. "
                    "Backfill missing questions or rerun Build My Learning Path first."
                )
            else:
                judge_tracker = NotebookProgressTracker(
                    title=f"Running yes/no answerability evaluation ({JUDGE_MAX_WORKERS} workers)",
                    total=judge_total,
                )
                start_time = time.time()
                result_rows = eval_utils.run_answerability_experiment(
                    hydrated_bundle,
                    client=judge_client,
                    model=judge_model,
                    modalities=MODALITIES,
                    max_workers=JUDGE_MAX_WORKERS,
                    progress_callback=judge_tracker.callback,
                )
                judge_elapsed = time.time() - start_time
                judge_tracker.complete(f"Judging completed in {judge_elapsed:.1f}s")

            results_df = pd.DataFrame(result_rows)
            print(f"Judged {len(results_df)} question-modality rows in {judge_elapsed:.1f}s")
            display(results_df.head(20))
            """
        ),
        code_cell(
            """
            summary = eval_utils.summarize_results(result_rows)

            overall_df = pd.DataFrame([summary["overall"]])
            modality_df = pd.DataFrame(summary["by_modality"])
            skill_type_df = pd.DataFrame(summary["by_skill_type"])
            difficulty_df = pd.DataFrame(summary["by_difficulty"])
            modality_difficulty_df = pd.DataFrame(summary["by_modality_and_difficulty"])

            if not modality_df.empty:
                modality_df = modality_df.sort_values("modality")
            if not skill_type_df.empty:
                skill_type_df = skill_type_df.sort_values("skill_type")
            if not difficulty_df.empty:
                difficulty_df = difficulty_df.sort_values("difficulty")
            if not modality_difficulty_df.empty:
                modality_difficulty_df = modality_difficulty_df.sort_values(
                    ["difficulty", "modality"]
                )

            display(Markdown("### Overall"))
            display(overall_df)

            display(Markdown("### By Modality"))
            display(modality_df)

            display(Markdown("### By Skill Type"))
            display(skill_type_df)

            display(Markdown("### By Difficulty"))
            display(difficulty_df)

            display(Markdown("### By Modality and Difficulty"))
            display(modality_difficulty_df)
            """
        ),
        markdown_cell(
            """
            ## Paper-Ready Tables

            The tables below convert rates to percentages so you can quickly move them into the results section or an appendix.
            """
        ),
        code_cell(
            """
            def percent_table(frame: pd.DataFrame, label_cols) -> pd.DataFrame:
                if frame.empty:
                    return frame
                if isinstance(label_cols, str):
                    label_cols = [label_cols]
                table = frame.copy()
                table["answerable_pct"] = (table["answerable_rate"] * 100).round(1)
                cols = [
                    *label_cols,
                    "judgments",
                    "answerable_yes_count",
                    "answerable_no_count",
                    "answerable_pct",
                ]
                return table[cols]

            modality_table_df = percent_table(modality_df, "modality")
            skill_type_table_df = percent_table(skill_type_df, "skill_type")
            difficulty_table_df = percent_table(difficulty_df, "difficulty")
            modality_difficulty_table_df = percent_table(
                modality_difficulty_df,
                ["difficulty", "modality"],
            )

            display(Markdown("### Modality Table"))
            display(modality_table_df)

            display(Markdown("### Skill Type Table"))
            display(skill_type_table_df)

            display(Markdown("### Difficulty Table"))
            display(difficulty_table_df)

            display(Markdown("### Difficulty x Modality Table"))
            display(modality_difficulty_table_df)
            """
        ),
        code_cell(
            """
            if not modality_df.empty:
                modality_fig = px.bar(
                    modality_df,
                    x="modality",
                    y="answerable_rate",
                    title="Answerable Questions by Modality",
                    text="answerable_rate",
                )
                modality_fig.update_xaxes(title_text="Resource Modality")
                modality_fig.update_yaxes(title_text="Answerable Rate")
                style_publication_figure(modality_fig)
                modality_fig.show()

            if not difficulty_df.empty:
                difficulty_fig = px.bar(
                    difficulty_df,
                    x="difficulty",
                    y="answerable_rate",
                    title="Answerable Questions by Question Difficulty",
                    text="answerable_rate",
                    category_orders={
                        "difficulty": ["easy", "medium", "hard"],
                    },
                )
                difficulty_fig.update_xaxes(title_text="Question Difficulty")
                difficulty_fig.update_yaxes(title_text="Answerable Rate")
                style_publication_figure(difficulty_fig)
                difficulty_fig.show()

            if not modality_difficulty_df.empty:
                modality_difficulty_fig = px.bar(
                    modality_difficulty_df,
                    x="difficulty",
                    y="answerable_rate",
                    color="modality",
                    barmode="group",
                    title="Answerable Questions by Difficulty and Modality",
                    text="answerable_rate",
                    category_orders={
                        "difficulty": ["easy", "medium", "hard"],
                        "modality": ["readings", "videos", "combined"],
                    },
                )
                modality_difficulty_fig.update_xaxes(title_text="Question Difficulty")
                modality_difficulty_fig.update_yaxes(title_text="Answerable Rate")
                style_publication_figure(modality_difficulty_fig)
                modality_difficulty_fig.show()
            """
        ),
        markdown_cell(
            """
            ## Worked Examples

            These examples make the evaluation protocol concrete. Each case shows whether the judge marked the question answerable, which evidence snippets supported that decision, and what information was missing when the answer was not learnable from the retrieved materials.
            """
        ),
        code_cell(
            """
            def display_worked_example(row: pd.Series, heading: str) -> None:
                supporting_quotes = row.get("supporting_quotes") or []
                quote_lines = (
                    "\\n".join(f"- {quote}" for quote in supporting_quotes[:3])
                    if supporting_quotes
                    else "- None provided"
                )
                display(
                    Markdown(
                        f"### {heading}\\n"
                        f"**Skill:** {row['skill_name']}  \\n"
                        f"**Question:** {row['question_text']}  \\n"
                        f"**Difficulty:** {row['difficulty']}  \\n"
                        f"**Modality:** {row['modality']}  \\n"
                        f"**Answerable:** `{row['answerable']}`  \\n"
                        f"**Evidence strength:** `{row['evidence_strength']}`  \\n"
                        f"**Confidence:** `{row['confidence']:.2f}`  \\n"
                        f"**Evidence chars sent to judge:** `{row['evidence_chars']}`  \\n"
                        f"**Resources passed to judge:** `{row['used_resource_count']}`\\n\\n"
                        f"**Judge reasoning**  \\n{row['reasoning']}\\n\\n"
                        f"**Supporting quotes**  \\n{quote_lines}\\n\\n"
                        f"**Missing information (if not answerable)**  \\n{row['missing_information'] or 'None'}"
                    )
                )
                resource_frame = pd.DataFrame(
                    {
                        "resource_title": row.get("used_resource_titles", []),
                        "resource_url": row.get("used_resource_urls", []),
                    }
                )
                if not resource_frame.empty:
                    display(resource_frame)

            if results_df.empty:
                print("No judged rows are available for worked examples.")
            else:
                used_indices = set()
                example_specs = [
                    (
                        "Answerable case",
                        results_df[results_df["answerable"]],
                    ),
                    (
                        "Not answerable case",
                        results_df[~results_df["answerable"]],
                    ),
                    (
                        "Weak video or hard-question failure",
                        results_df[
                            ((results_df["modality"] == "videos") & (~results_df["answerable"]))
                            | ((results_df["difficulty"] == "hard") & (~results_df["answerable"]))
                        ],
                    ),
                ]

                for heading, candidate_df in example_specs:
                    candidate_df = candidate_df.loc[
                        ~candidate_df.index.isin(used_indices)
                    ].head(1)
                    if candidate_df.empty:
                        display(Markdown(f"### {heading}\\nNo case matched this filter in the current run."))
                        continue
                    row = candidate_df.iloc[0]
                    used_indices.add(candidate_df.index[0])
                    display_worked_example(row, heading)
            """
        ),
        markdown_cell(
            """
            ## Failure Analysis

            These views are useful for qualitative analysis and for selecting examples to discuss in the paper.
            """
        ),
        code_cell(
            """
            audit_columns = [
                "skill_name",
                "skill_type",
                "question_id",
                "difficulty",
                "modality",
                "answerable",
                "evidence_strength",
                "confidence",
                "used_resource_count",
                "evidence_chars",
                "supporting_quotes",
                "missing_information",
                "used_resource_titles",
                "reasoning",
            ]

            if results_df.empty:
                print("No result rows are available for failure analysis.")
            else:
                combined_df = results_df[results_df["modality"] == "combined"].copy()

                display(Markdown("### Combined Modality Not-Answerable Cases"))
                display(combined_df[~combined_df["answerable"]][audit_columns].head(20))

                display(Markdown("### Not-Answerable Cases Across All Modalities"))
                display(results_df[~results_df["answerable"]][audit_columns].head(20))
            """
        ),
        code_cell(
            """
            artifact_paths = eval_utils.save_artifacts(
                repo_root=REPO_ROOT,
                bundle=hydrated_bundle,
                rows=result_rows,
                summary=summary,
                artifact_prefix=ARTIFACT_PREFIX,
            )
            artifact_paths
            """
        ),
        markdown_cell(
            """
            ## Reporting Guidance

            Suggested interpretation discipline for the paper:

            - Treat answerable rate as the main proxy for resource sufficiency, not as a perfect ground-truth label.
            - Report answerable counts and percentages by modality and by difficulty.
            - Use the `missing_information` field to explain why videos or readings fail on harder questions.
            - Mention when videos rely on transcript fallback versus search metadata fallback.
            - Include at least a small manual audit of judged cases in the appendix or methods section.
            - If a skill has zero usable evidence, report that as a retrieval coverage failure rather than a judge failure.
            """
        ),
        code_cell(
            """
            driver.close()
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
