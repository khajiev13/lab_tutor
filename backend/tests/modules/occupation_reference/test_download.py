import httpx
import pytest


def test_download_uses_pinned_urls_and_safe_cache(fixture_dir, tmp_path):
    from app.modules.occupation_reference.importer import (
        download_release,
        parse_release,
    )

    requested = []

    def respond(request):
        requested.append(str(request.url))
        return httpx.Response(
            200,
            content=(fixture_dir / request.url.path.rsplit("/", 1)[-1]).read_bytes(),
            headers={"Content-Type": "text/csv"},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        directory = download_release("31.0", tmp_path, client)
        assert len(parse_release(directory, "31.0").evidence) == 4
        with pytest.raises(ValueError):
            download_release("../31.0", tmp_path, client)
    assert len(requested) == 7
    assert all(
        url.startswith("https://www.onetcenter.org/dl_files/database/db_31_0_csv/")
        for url in requested
    )


@pytest.mark.parametrize(
    "headers,content",
    [
        ({"Content-Type": "text/html"}, b"<html>error</html>"),
        ({"Content-Type": "text/csv", "Content-Length": "1000"}, b"short"),
    ],
)
def test_html_truncated_body_and_failed_download_do_not_publish(
    tmp_path, headers, content
):
    from app.modules.occupation_reference.importer import download_release

    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers=headers, content=content)
            )
        ) as client,
        pytest.raises(ValueError),
    ):
        download_release("31.0", tmp_path, client)
    assert not (tmp_path / "31.0" / "occupation_data.csv").exists()


def test_download_retries_are_bounded(tmp_path, monkeypatch):
    from app.modules.occupation_reference import importer

    calls = []
    monkeypatch.setattr(importer.time, "sleep", lambda seconds: None)

    def respond(request):
        calls.append(request)
        return httpx.Response(503)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises((ValueError, httpx.HTTPStatusError)),
    ):
        importer.download_release("31.0", tmp_path, client)
    assert len(calls) == 3


def test_download_cannot_replace_existing_immutable_release(fixture_dir, tmp_path):
    import shutil

    from app.modules.occupation_reference.importer import download_release

    shutil.copytree(fixture_dir, tmp_path / "31.0")
    original = (tmp_path / "31.0" / "occupation_data.csv").read_bytes()

    def respond(request):
        filename = request.url.path.rsplit("/", 1)[-1]
        content = (fixture_dir / filename).read_bytes()
        if filename == "occupation_data.csv":
            content += b"\n"
        return httpx.Response(
            200, content=content, headers={"Content-Type": "text/csv"}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(ValueError),
    ):
        download_release("31.0", tmp_path, client)
    assert (tmp_path / "31.0" / "occupation_data.csv").read_bytes() == original
