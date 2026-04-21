from app.modules.student_learning_path.notebooks import (
    generate_reading_react_tutor_notebook,
)


def test_generated_reading_react_tutor_notebook_has_expected_structure():
    notebook = generate_reading_react_tutor_notebook.build_notebook()
    markdown_text = "\n".join(
        cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "markdown"
    )
    code_text = "\n".join(
        cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "code"
    )

    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile(cell["source"], "<notebook-cell>", "exec")

    for helper_name in [
        "discover_reading_sessions",
        "load_reading_session_bundle",
        "fetch_reading_markdown_for_session",
        "build_reading_chunks",
        "build_thread_id",
        "run_tutor_turn",
    ]:
        assert f"def {helper_name}" in code_text

    assert "create_react_agent" in code_text
    assert "extract_reading_markdown" in code_text
    assert "search_reading_chunks" in code_text
    assert "student-{student_id}:reading-{reading_id}" in code_text
    assert "reading-agent/thread/{thread_id}" in markdown_text
    assert "/users/me" in markdown_text
    assert "ReAct tutor" in markdown_text
