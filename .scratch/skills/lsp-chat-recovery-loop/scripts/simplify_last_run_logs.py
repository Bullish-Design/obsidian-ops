#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_LOGS_DIR = Path("/home/andrew/Documents/Projects/remora/.remora/logs")
DEFAULT_DROP_PATTERNS = (
    r"Event NodeDiscoveredEvent .* matched 0 agents: \[\]",
    r"EventBus\.emit: NodeDiscoveredEvent agent_id=None",
    r"EventBus\.emit: 0 handlers for NodeDiscoveredEvent",
)
TIMESTAMP_RE = re.compile(
    r"^(server|client)-(\d{4}-\d{2}-\d{2})_(\d{6})\.log$"
)


@dataclass
class FileStats:
    source: str
    destination: str
    total_lines: int = 0
    kept_lines: int = 0
    dropped_lines: int = 0
    dropped_by_pattern: dict[str, int] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simplify latest Remora server/client logs by removing known low-signal noise."
        )
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=DEFAULT_LOGS_DIR,
        help=f"Log directory (default: {DEFAULT_LOGS_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Destination directory for simplified logs and summary JSON.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of latest server logs and client logs to include (default: 1).",
    )
    parser.add_argument(
        "--drop-regex",
        action="append",
        default=[],
        help="Additional line-drop regex; repeat for multiple patterns.",
    )
    parser.add_argument(
        "--suffix",
        default=".simplified",
        help="Suffix inserted before .log (default: .simplified).",
    )
    return parser.parse_args()


def parse_timestamp_from_name(path: Path) -> datetime:
    match = TIMESTAMP_RE.match(path.name)
    if not match:
        return datetime.min
    date_part = match.group(2)
    time_part = match.group(3)
    return datetime.strptime(f"{date_part}_{time_part}", "%Y-%m-%d_%H%M%S")


def select_latest_logs(logs_dir: Path, count: int) -> list[Path]:
    if count < 1:
        raise ValueError("--count must be >= 1")

    server_logs = sorted(
        logs_dir.glob("server-*.log"),
        key=parse_timestamp_from_name,
    )
    client_logs = sorted(
        logs_dir.glob("client-*.log"),
        key=parse_timestamp_from_name,
    )
    selected = server_logs[-count:] + client_logs[-count:]
    unique_sorted = sorted(set(selected), key=parse_timestamp_from_name)
    if not unique_sorted:
        raise FileNotFoundError(f"No matching logs found in {logs_dir}")
    return unique_sorted


def compile_patterns(extra_patterns: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = list(DEFAULT_DROP_PATTERNS)
    patterns.extend(extra_patterns)
    return [(pattern, re.compile(pattern)) for pattern in patterns]


def first_match(line: str, patterns: list[tuple[str, re.Pattern[str]]]) -> str | None:
    for label, regex in patterns:
        if regex.search(line):
            return label
    return None


def output_name(source: Path, suffix: str) -> str:
    if source.suffix == ".log":
        return f"{source.stem}{suffix}.log"
    return f"{source.name}{suffix}"


def simplify_file(
    source: Path,
    destination: Path,
    patterns: list[tuple[str, re.Pattern[str]]],
) -> FileStats:
    stats = FileStats(source=str(source), destination=str(destination))
    kept_lines: list[str] = []

    with source.open("r", encoding="utf-8", errors="replace") as infile:
        for line in infile:
            stats.total_lines += 1
            match = first_match(line, patterns)
            if match is None:
                kept_lines.append(line)
                stats.kept_lines += 1
                continue

            stats.dropped_lines += 1
            stats.dropped_by_pattern[match] = stats.dropped_by_pattern.get(match, 0) + 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as outfile:
        outfile.writelines(kept_lines)

    return stats


def write_summary(path: Path, files: list[FileStats]) -> None:
    payload = {
        "files": [
            {
                "source": item.source,
                "destination": item.destination,
                "total_lines": item.total_lines,
                "kept_lines": item.kept_lines,
                "dropped_lines": item.dropped_lines,
                "dropped_by_pattern": item.dropped_by_pattern,
            }
            for item in files
        ],
        "totals": {
            "total_lines": sum(item.total_lines for item in files),
            "kept_lines": sum(item.kept_lines for item in files),
            "dropped_lines": sum(item.dropped_lines for item in files),
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    logs_dir = args.logs_dir.resolve()
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    input_logs = select_latest_logs(logs_dir, args.count)
    patterns = compile_patterns(args.drop_regex)
    stats: list[FileStats] = []

    print("Selected logs:")
    for log_file in input_logs:
        print(f"- {log_file}")
        destination = out_dir / output_name(log_file, args.suffix)
        stat = simplify_file(log_file, destination, patterns)
        stats.append(stat)

    summary_path = out_dir / "simplify_summary.json"
    write_summary(summary_path, stats)

    print("\nResults:")
    for item in stats:
        src_name = Path(item.source).name
        print(
            f"- {src_name}: kept={item.kept_lines} dropped={item.dropped_lines} total={item.total_lines}"
        )
    print(f"\nSummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
