from app.modules.courses.file_processing import infer_file_kind


def test_infer_file_kind_txt_by_extension():
    r = infer_file_kind(filename="notes.TXT", content_type=None)
    assert r.kind == "txt"


def test_infer_file_kind_ppt_by_extension():
    r = infer_file_kind(filename="slides.pptx", content_type=None)
    assert r.kind == "ppt"


def test_infer_file_kind_txt_by_content_type():
    r = infer_file_kind(filename="noext", content_type="text/plain")
    assert r.kind == "txt"
