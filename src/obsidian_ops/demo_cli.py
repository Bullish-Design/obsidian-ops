"""Typer CLI for the obsidian-ops demo workflow."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer

app = typer.Typer(name="demo", help="Run and manage the obsidian-ops demo.")


@dataclass(frozen=True)
class DemoPaths:
    repo_root: Path
    demo_root: Path
    source_vault: Path
    gen_root: Path
    site_root: Path
    work_root: Path
    runtime_vault: Path


def _resolve_paths() -> DemoPaths:
    repo_root = Path(__file__).resolve().parents[2]
    demo_root = repo_root / "demo" / "obsidian-ops"
    gen_root = repo_root / "gen" / "obsidian-ops"
    site_root = gen_root / "site"
    work_root = repo_root / ".scratch" / "projects" / "06-demo-scaffold" / "generated"
    runtime_vault = work_root / "runtime-vault"
    return DemoPaths(
        repo_root=repo_root,
        demo_root=demo_root,
        source_vault=demo_root / "vault",
        gen_root=gen_root,
        site_root=site_root,
        work_root=work_root,
        runtime_vault=runtime_vault,
    )


def _run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    typer.echo("  $ " + " ".join(command))
    result = subprocess.run(command, cwd=str(cwd), env=env)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _cleanup(paths: DemoPaths) -> list[Path]:
    removed: list[Path] = []
    for target in (paths.gen_root, paths.work_root):
        if target.exists():
            shutil.rmtree(target)
            removed.append(target)
    return removed


def _prepare_runtime_vault(paths: DemoPaths) -> None:
    if not paths.source_vault.exists():
        typer.echo(f"Error: demo source vault not found: {paths.source_vault}", err=True)
        raise typer.Exit(1)

    paths.work_root.mkdir(parents=True, exist_ok=True)
    if paths.runtime_vault.exists():
        shutil.rmtree(paths.runtime_vault)
    shutil.copytree(paths.source_vault, paths.runtime_vault)

    _run_command(["jj", "git", "init"], paths.runtime_vault)


def _run_server(paths: DemoPaths, host: str, port: int) -> None:
    paths.site_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OPS_VAULT_DIR"] = str(paths.runtime_vault)
    env["OPS_SITE_DIR"] = str(paths.site_root)
    env["OPS_HOST"] = host
    env["OPS_PORT"] = str(port)

    typer.echo("")
    typer.echo("Demo runtime:")
    typer.echo(f"  vault: {paths.runtime_vault}")
    typer.echo(f"  site:  {paths.site_root}")
    typer.echo(f"  url:   http://{host}:{port}/")
    typer.echo("")
    _run_command(
        ["uvicorn", "obsidian_ops.app:app", "--host", host, "--port", str(port)],
        cwd=paths.repo_root,
        env=env,
    )


@app.command()
def cleanup() -> None:
    """Remove generated demo runtime and site output."""
    paths = _resolve_paths()
    removed = _cleanup(paths)
    if not removed:
        typer.echo("No generated demo outputs to remove.")
        return
    typer.echo("Removed:")
    for item in removed:
        typer.echo(f"  - {item}")


@app.command()
def run(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
    cleanup_first: bool = typer.Option(True, "--cleanup/--no-cleanup"),
) -> None:
    """Prepare demo runtime vault and run obsidian-ops server."""
    paths = _resolve_paths()
    if cleanup_first:
        _cleanup(paths)
    _prepare_runtime_vault(paths)
    _run_server(paths, host, port)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
    run_first: bool = typer.Option(False, "--run-first"),
) -> None:
    """Serve existing demo runtime; optionally recreate it first."""
    paths = _resolve_paths()
    if run_first:
        _cleanup(paths)
        _prepare_runtime_vault(paths)

    if not paths.runtime_vault.exists():
        typer.echo("Error: no demo runtime found. Run 'demo run' first or pass --run-first.", err=True)
        raise typer.Exit(1)

    _run_server(paths, host, port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
