from __future__ import annotations

from pathlib import Path

MARKER = "<!-- ops-overlay -->"
INJECTION = (
    "<!-- ops-overlay -->\n"
    '<link rel="stylesheet" href="/ops/ops.css">\n'
    '<script src="/ops/ops.js" defer></script>\n'
)


def inject_overlay(site_dir: Path) -> int:
    modified = 0
    for html_file in site_dir.rglob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        if MARKER in content:
            continue

        lower_content = content.lower()
        head_close_idx = lower_content.find("</head>")
        if head_close_idx == -1:
            continue

        updated = content[:head_close_idx] + INJECTION + content[head_close_idx:]
        html_file.write_text(updated, encoding="utf-8")
        modified += 1

    return modified
