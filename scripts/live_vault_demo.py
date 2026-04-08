#!/usr/bin/env python3
"""Run a live, step-by-step obsidian-ops demo against a runtime vault copy."""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SOURCE_VAULT = REPO_ROOT / "demo" / "obsidian-ops" / "vault"
DEFAULT_RUNTIME_ROOT = REPO_ROOT / ".scratch" / "projects" / "16-live-demo-script" / "generated"
LIVE_NOTE_REL = Path("live-demo/live-ops.md")
TEMP_NOTE_REL = Path("live-demo/temp-to-delete.md")
NEW_NOTE_REL = Path("live-demo/new-note.md")

LIVE_NOTE_TEMPLATE = textwrap.dedent(
    """\
    ---
    title: Live Ops Demo
    status: draft
    owner: ops-team
    tags: [demo, live]
    ---

    # Live Ops Demo

    This note is used by the live mutation demo script.

    ## Agenda

    - Introduce the demo vault
    - Watch changes appear in real time
    - Confirm reset and cleanup behavior

    ## Notes

    This paragraph contains a block reference. ^demo-block

    - First checklist item
    - Replace me during demo ^demo-list
    - Third checklist item
    """
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def log(runtime_root: Path, line: str) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    log_path = runtime_root / "demo.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {line}\n")


def reset_runtime_vault(runtime_root: Path) -> Path:
    runtime_vault = runtime_root / "vault"
    if runtime_vault.exists():
        shutil.rmtree(runtime_vault)

    runtime_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_VAULT, runtime_vault)

    live_note_abs = runtime_vault / LIVE_NOTE_REL
    live_note_abs.parent.mkdir(parents=True, exist_ok=True)
    live_note_abs.write_text(LIVE_NOTE_TEMPLATE, encoding="utf-8")

    temp_note_abs = runtime_vault / TEMP_NOTE_REL
    temp_note_abs.parent.mkdir(parents=True, exist_ok=True)
    temp_note_abs.write_text("# Temporary Demo Note\n\nThis file will be deleted by the demo run.\n", encoding="utf-8")

    log(runtime_root, f"Reset runtime vault at {runtime_vault}")
    return runtime_vault


def cleanup_runtime(runtime_root: Path) -> None:
    if runtime_root.exists():
        shutil.rmtree(runtime_root)


def sleep_between(delay_s: float) -> None:
    if delay_s > 0:
        time.sleep(delay_s)


def run_demo(runtime_root: Path, delay_s: float, no_reset: bool) -> int:
    try:
        from obsidian_ops.vault import Vault
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "obsidian_ops dependencies are missing. Run inside devenv "
            "or sync dependencies first (e.g. `devenv shell -- uv sync --extra dev`)."
        ) from exc

    runtime_vault = runtime_root / "vault"
    if not no_reset or not runtime_vault.exists():
        runtime_vault = reset_runtime_vault(runtime_root)

    vault = Vault(runtime_vault)
    step = 1

    print("Live vault demo starting.")
    print(f"Open this vault in Obsidian: {runtime_vault}")
    print(f"Watch this note: {runtime_vault / LIVE_NOTE_REL}")
    print("")
    log(runtime_root, f"Demo run started against {runtime_vault}")

    def announce(name: str) -> None:
        nonlocal step
        print(f"[Step {step:02d}] {name}")
        log(runtime_root, f"Step {step:02d}: {name}")
        step += 1

    announce("Read the live note")
    initial = vault.read_file(str(LIVE_NOTE_REL))
    print(f"  Read {len(initial)} chars from {LIVE_NOTE_REL}")
    sleep_between(delay_s)

    announce("List live-demo markdown files")
    files = vault.list_files("live-demo/*.md")
    print(f"  Found files: {files}")
    sleep_between(delay_s)

    announce("Search for 'block reference' across live-demo notes")
    results = vault.search_files("block reference", glob="live-demo/*.md")
    print(f"  Search hits: {[item.path for item in results]}")
    sleep_between(delay_s)

    announce("Create a new note")
    new_note_content = (
        "---\n"
        "title: Generated During Demo\n"
        "status: active\n"
        "---\n\n"
        "# Generated During Demo\n\n"
        f"Created at {now_iso()}.\n"
    )
    vault.write_file(str(NEW_NOTE_REL), new_note_content)
    print(f"  Wrote {NEW_NOTE_REL}")
    sleep_between(delay_s)

    announce("Update frontmatter fields on the live note")
    vault.update_frontmatter(
        str(LIVE_NOTE_REL),
        {
            "status": "in-review",
            "last_demo_run": now_iso(),
        },
    )
    print("  Updated status and last_demo_run")
    sleep_between(delay_s)

    announce("Delete one frontmatter field")
    vault.delete_frontmatter_field(str(LIVE_NOTE_REL), "owner")
    print("  Removed frontmatter field: owner")
    sleep_between(delay_s)

    announce("Replace the ## Agenda section")
    vault.write_heading(
        str(LIVE_NOTE_REL),
        "## Agenda",
        "- Confirm vault path in Obsidian\n- Observe file writes\n- Observe block update\n- Observe deletion\n",
    )
    print("  Agenda section replaced")
    sleep_between(delay_s)

    announce("Replace a paragraph block by block-id")
    vault.write_block(
        str(LIVE_NOTE_REL),
        "^demo-block",
        f"This block was updated by the live demo at {now_iso()}. ^demo-block",
    )
    print("  Paragraph block updated")
    sleep_between(delay_s)

    announce("Replace a list item block by block-id")
    vault.write_block(
        str(LIVE_NOTE_REL),
        "^demo-list",
        "- Updated checklist item written by live demo ^demo-list",
    )
    print("  List item block updated")
    sleep_between(delay_s)

    announce("Delete the temporary note")
    vault.delete_file(str(TEMP_NOTE_REL))
    print(f"  Deleted {TEMP_NOTE_REL}")
    sleep_between(delay_s)

    announce("Report lock state")
    print(f"  is_busy() -> {vault.is_busy()}")

    log(runtime_root, "Demo run completed")
    print("")
    print("Demo complete.")
    print(f"Runtime vault remains at: {runtime_vault}")
    print("Run reset to restore baseline: ops-live-demo reset")
    print("Run cleanup to remove runtime files: ops-live-demo cleanup")
    return 0


def status(runtime_root: Path) -> int:
    runtime_vault = runtime_root / "vault"
    print(f"Source vault:  {SOURCE_VAULT}")
    print(f"Runtime root:  {runtime_root}")
    print(f"Runtime vault: {runtime_vault}")
    print(f"Exists:        {runtime_vault.exists()}")
    if runtime_vault.exists():
        live_note_abs = runtime_vault / LIVE_NOTE_REL
        print(f"Live note:     {live_note_abs}")
        print(f"Live note exists: {live_note_abs.exists()}")
    log(runtime_root, "Status inspected")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live obsidian-ops vault mutation demo.")
    parser.add_argument(
        "--runtime-root",
        default=str(DEFAULT_RUNTIME_ROOT),
        help=f"Runtime root for generated demo data (default: {DEFAULT_RUNTIME_ROOT})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full step-by-step mutation demo.")
    run_parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between steps (default: 1.5)")
    run_parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not reset the runtime vault before running steps.",
    )

    subparsers.add_parser("reset", help="Reset runtime vault from source demo vault.")
    subparsers.add_parser("cleanup", help="Remove all generated runtime demo files.")
    subparsers.add_parser("status", help="Show source/runtime paths and current runtime status.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    runtime_root = Path(args.runtime_root).resolve()

    if args.command == "run":
        return run_demo(runtime_root=runtime_root, delay_s=args.delay, no_reset=args.no_reset)
    if args.command == "reset":
        runtime_vault = reset_runtime_vault(runtime_root)
        print(f"Runtime vault reset at: {runtime_vault}")
        print(f"Open this vault in Obsidian: {runtime_vault}")
        return 0
    if args.command == "cleanup":
        cleanup_runtime(runtime_root)
        print(f"Removed runtime demo data: {runtime_root}")
        return 0
    if args.command == "status":
        return status(runtime_root)

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
