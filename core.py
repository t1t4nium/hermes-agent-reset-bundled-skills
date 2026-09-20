"""Core operations for reinstalling bundled skills.

The logic lives here, free of argparse and terminal output, so it can be tested
independently. Hermes internals are imported lazily inside functions so this module
stays importable without a fully wired Hermes runtime.

Why this exists: the curator (with ``curator.prune_builtins``) archives unused bundled
skills into ``~/.hermes/skills/.archive/`` and records them in ``.curator_suppressed``.
``hermes curator restore`` moves them back flat (losing the category directory), and
``hermes skills reset --restore`` is per-skill and blocked by ``.curator_suppressed``.
This module does the whole job in one pass, preserving category directories.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

_TIMESTAMP_SUFFIX_LEN = 14  # ``<name>-YYYYMMDDHHMMSS`` archive collision suffix


def _skills_dir() -> Path:
    from tools.skill_usage import _skills_dir as _impl

    return _impl()


def _archive_dir() -> Path:
    from tools.skill_usage import _archive_dir as _impl

    return _impl()


def _base_skill_name(dirname: str) -> str:
    """Strip a timestamp collision suffix so ``dogfood-20240901120000`` reads as ``dogfood``."""
    if len(dirname) > _TIMESTAMP_SUFFIX_LEN + 1 and dirname[-_TIMESTAMP_SUFFIX_LEN - 1] == "-":
        suffix = dirname[-_TIMESTAMP_SUFFIX_LEN:]
        if suffix.isdigit():
            return dirname[: -_TIMESTAMP_SUFFIX_LEN - 1]
    return dirname


def _archive_paths_for(name: str) -> List[Path]:
    """Every directory under ``.archive/`` that belongs to *name* (exact or timestamped)."""
    archive = _archive_dir()
    if not archive.exists():
        return []
    out: List[Path] = []
    for child in archive.iterdir():
        if not child.is_dir():
            continue
        if _base_skill_name(child.name) == name:
            out.append(child)
    return out


def _bundled_archive_names() -> List[str]:
    """Bundled skill names that currently have a directory under ``.archive/``."""
    from tools.skill_usage import is_bundled

    archive = _archive_dir()
    if not archive.exists():
        return []
    names = {_base_skill_name(child.name) for child in archive.iterdir() if child.is_dir()}
    return sorted(name for name in names if is_bundled(name))


def collect_plan(overwrite_modified: bool) -> Dict[str, List[str]]:
    """Compute what a reset would touch, without mutating anything.

    Returns ``{"pruned": [...], "modified": [...]}``.
    """
    from tools.skill_usage import is_bundled, read_suppressed_names
    from tools.skills_sync_bundled_ops import list_user_modified_bundled_skills

    suppressed = read_suppressed_names()
    pruned = sorted(name for name in suppressed if is_bundled(name))
    modified: List[str] = []
    if overwrite_modified:
        modified = [entry["name"] for entry in list_user_modified_bundled_skills()]
    return {"pruned": pruned, "modified": modified}


def status() -> Dict[str, Any]:
    """Counters for the ``status`` subcommand. Read-only."""
    from tools.skill_usage import is_bundled, read_suppressed_names
    from tools.skills_sync_bundled_ops import list_user_modified_bundled_skills
    from tools.skills_sync import _read_manifest

    suppressed = read_suppressed_names()
    pruned = sorted(name for name in suppressed if is_bundled(name))
    modified = [entry["name"] for entry in list_user_modified_bundled_skills()]
    archive = _archive_dir()
    archive_bundled = 0
    archive_other = 0
    if archive.exists():
        for child in archive.iterdir():
            if not child.is_dir():
                continue
            if is_bundled(_base_skill_name(child.name)):
                archive_bundled += 1
            else:
                archive_other += 1
    return {
        "bundled_total": len(_read_manifest()),
        "pruned": pruned,
        "modified": modified,
        "archive_bundled": archive_bundled,
        "archive_other": archive_other,
    }


def apply(overwrite_modified: bool) -> Dict[str, Any]:
    """Execute the reset. Idempotent: a second run is a no-op.

    Returns counters and the sync report.
    """
    from tools.skill_usage import _toggle_suppressed_name, forget, is_bundled, read_suppressed_names
    from tools.skills_sync import _read_manifest, _rmtree_writable, _write_manifest, sync_skills
    from tools.skills_sync_bundled_ops import list_user_modified_bundled_skills

    suppressed = read_suppressed_names()
    pruned = sorted(name for name in suppressed if is_bundled(name))
    modified = [entry["name"] for entry in list_user_modified_bundled_skills()] if overwrite_modified else []

    manifest = _read_manifest()

    # Stop the re-seeder from skipping the pruned skills.
    for name in pruned:
        _toggle_suppressed_name(name, add=False)

    # Drop the archived copies of bundled skills (optional/hub archive entries are untouched).
    # Deletes stale entries too, not only the suppressed ones, so a prior manual
    # ``hermes skills reset --restore`` cannot leave a dead archive copy behind.
    archive_removed: List[str] = []
    for name in _bundled_archive_names():
        for path in _archive_paths_for(name):
            _rmtree_writable(path)
        archive_removed.append(name)

    # Forget manifest entries so sync treats these skills as new and re-copies them.
    for name in pruned + modified:
        manifest.pop(name, None)
    _write_manifest(manifest)

    # Overwrite edited copies with stock when requested.
    if overwrite_modified:
        for entry in list_user_modified_bundled_skills():
            if entry["name"] in modified:
                dest = Path(entry["dest"])
                if dest.exists():
                    _rmtree_writable(dest)

    sync_result = sync_skills(quiet=True)

    # Reset curator state for restored skills (drop the stale "archived" usage record).
    for name in pruned:
        forget(name)

    return {
        "restored": pruned,
        "overwritten": modified,
        "archive_removed": archive_removed,
        "copied": sync_result.get("copied", []),
        "updated": sync_result.get("updated", []),
        "user_modified": sync_result.get("user_modified", []),
        "suppressed": sync_result.get("suppressed", []),
    }
