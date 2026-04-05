from __future__ import annotations

from pathlib import Path

from obsidian_ops.inject import inject_overlay


def test_injects_overlay_before_head_close(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<html><head><title>X</title></head><body></body></html>", encoding="utf-8")

    count = inject_overlay(tmp_path)

    assert count == 1
    content = html.read_text(encoding="utf-8")
    assert "<!-- ops-overlay -->" in content
    assert content.index("<!-- ops-overlay -->") < content.lower().index("</head>")


def test_already_injected_file_is_skipped(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        "<html><head><!-- ops-overlay --><script src=\"/ops/ops.js\"></script></head><body></body></html>",
        encoding="utf-8",
    )

    count = inject_overlay(tmp_path)

    assert count == 0


def test_file_without_head_is_skipped(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<html><body>No head</body></html>", encoding="utf-8")

    count = inject_overlay(tmp_path)

    assert count == 0


def test_returns_count_of_modified_files(tmp_path: Path) -> None:
    (tmp_path / "a.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    (tmp_path / "b.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    (tmp_path / "c.html").write_text("<html><body></body></html>", encoding="utf-8")

    count = inject_overlay(tmp_path)

    assert count == 2
