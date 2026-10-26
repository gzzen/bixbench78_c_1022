# Path: common/integrity/freeze.py
# Purpose: Hash answer-blind generation artifacts before any private post-hoc scoring.
from __future__ import annotations
from pathlib import Path
from .hashing import sha256_file

def freeze_files(root: Path, files: list[Path]) -> list[dict[str, str]]:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)} for path in files if path.is_file()]


def frozen_workspace(recorded: str | Path, root: Path) -> Path:
    """Locate a generation's recorded workspace inside this checkout.

    Generations record absolute workspace paths, but freeze manifests are
    checkout-relative.  When a run tree is copied to another checkout, read the
    copy under ``root/runs`` (the files the freeze manifest verifies), not the
    stale absolute path.  A workspace found nowhere is an error, never an empty result.
    """
    path = Path(recorded)
    if path.is_absolute() and not path.resolve().is_relative_to(root.resolve()):
        parts = path.parts
        for index in [i for i, part in enumerate(parts) if part == "runs"]:
            candidate = root.joinpath(*parts[index:])
            if candidate.is_dir():
                return candidate
    if not path.is_dir():
        raise RuntimeError(f"frozen workspace not found in this checkout or at its recorded path: {recorded}")
    return path
