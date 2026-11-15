"""scripts/data-code-changed.sh decides when Jenkins must refresh the model."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "data-code-changed.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, relative: str, body: str = "x\n") -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", relative)


def _changed(repo: Path) -> int:
    return subprocess.run(
        ["sh", str(SCRIPT), "HEAD~1", "HEAD"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    ).returncode


def test_site_only_change_skips_refresh(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _commit(tmp_path, "README.md", "base\n")
    _commit(tmp_path, "pa_edu/web/app.js", "console.log(1)\n")
    assert _changed(tmp_path) == 1


def test_extract_change_needs_refresh(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _commit(tmp_path, "README.md", "base\n")
    _commit(tmp_path, "pa_edu/extract.py", "print('extract')\n")
    assert _changed(tmp_path) == 0


def test_publish_module_alone_skips_refresh(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _commit(tmp_path, "README.md", "base\n")
    _commit(tmp_path, "pa_edu/publish.py", "print('publish')\n")
    assert _changed(tmp_path) == 1
