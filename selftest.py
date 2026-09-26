"""Self-test for the reset-bundled-skills plugin.

Runs the recipe end-to-end inside a throwaway Hermes home, using only the standard
library and Hermes internals (no pytest). Returns 0 on success, 1 on failure. Invoked
by ``hermes reset-bundled-skills-selftest``.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import List


def _load_core():
    try:
        from . import core
    except ImportError:  # standalone execution, outside the plugin package
        import core
    return core


def _pick_skills(count: int) -> List[str]:
    """Pick *count* bundled skill names from the manifest, excluding essentials and
    protected built-ins so the assertions hold as the manifest evolves over time."""
    from agent.skill_utils import ESSENTIAL_SKILLS
    from tools.skill_usage import is_protected_builtin
    from tools.skills_sync import _read_manifest

    candidates = sorted(
        name
        for name in _read_manifest()
        if name not in ESSENTIAL_SKILLS and not is_protected_builtin(name)
    )
    return candidates[:count]


def run() -> int:
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from tools.skill_usage import _archive_dir, _find_skill_dir, _skills_dir, _toggle_suppressed_name
    from tools.skills_sync import _dir_hash, sync_skills

    core = _load_core()
    failures: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))
        if not ok:
            failures.append(name)

    print("reset-bundled-skills self-test")

    names = _pick_skills(7)
    if len(names) < 7:
        print(f"  [SKIP] only {len(names)} eligible bundled skill(s), need 7")
        return 0
    prune_names = names[:5]
    mod_name = names[5]
    missing_name = names[6]

    home = Path(tempfile.mkdtemp(prefix="rbs-selftest-"))
    token = set_hermes_home_override(home)
    try:
        skills_dir = _skills_dir()

        # Baseline: seed the tree and manifest from the bundled source.
        sync_skills(quiet=True)

        # Seed: simulate the curator pruning five bundled skills.
        for name in prune_names:
            live = _find_skill_dir(name)
            if live is None:
                check(f"seed {name}", False, "not found after sync")
                continue
            archive = _archive_dir()
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(live), str(archive / name))
            _toggle_suppressed_name(name, add=True)

        # Seed: simulate an edited bundled skill.
        mod_dir = _find_skill_dir(mod_name)
        if mod_dir is None:
            check(f"seed {mod_name}", False, "not found after sync")
            return 1
        stock_hash = _dir_hash(mod_dir)
        skill_md = mod_dir / "SKILL.md"
        skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")

        # Seed: simulate a user-deleted bundled skill (directory gone, manifest entry kept,
        # NOT suppressed, NOT archived) -- the "missing" state the sync refuses to re-add.
        missing_dir = _find_skill_dir(missing_name)
        if missing_dir is None:
            check(f"seed {missing_name}", False, "not found after sync")
            return 1
        shutil.rmtree(missing_dir)

        # 1. status reflects the seeded state.
        stats = core.status()
        check(
            "status pruned",
            set(stats["pruned"]) == set(prune_names),
            f"expected {sorted(prune_names)}, got {sorted(stats['pruned'])}",
        )
        check("status modified", stats["modified"] == [mod_name], f"got {stats['modified']}")
        check("status missing", stats["missing"] == [missing_name], f"got {stats['missing']}")

        # 2. plan without overwrite/restore-missing excludes the modified and missing skills.
        plan = core.collect_plan(overwrite_modified=False, restore_missing=False)
        check("plan pruned only", set(plan["pruned"]) == set(prune_names)
              and plan["modified"] == [] and plan["missing"] == [])

        # 3. plan with overwrite includes the modified skill, still no missing.
        plan_ow = core.collect_plan(overwrite_modified=True, restore_missing=False)
        check("plan includes modified", plan_ow["modified"] == [mod_name] and plan_ow["missing"] == [])

        # 4. plan with restore-missing includes the missing skill.
        plan_missing = core.collect_plan(overwrite_modified=False, restore_missing=True)
        check("plan includes missing", plan_missing["missing"] == [missing_name])

        # 5. apply without restore-missing restores pruned, leaves the edit and the
        #    missing skill alone.
        result = core.apply(overwrite_modified=False, restore_missing=False)
        check("apply restored count", len(result["restored"]) == len(prune_names))
        check("apply reinstalled none", result["reinstalled"] == [])
        for name in prune_names:
            restored_dir = _find_skill_dir(name)
            if restored_dir is None:
                check(f"restore {name} category", False, "missing")
            elif restored_dir.parent == skills_dir:
                check(f"restore {name} category", False, "flat (category lost)")
            else:
                check(f"restore {name} category", True)
        mod_after = (_find_skill_dir(mod_name) / "SKILL.md").read_text(encoding="utf-8")
        check("edit kept without overwrite", "# local edit" in mod_after)
        check("missing still missing", _find_skill_dir(missing_name) is None)

        # 6. idempotency.
        stats_after = core.status()
        check("idempotent no pruned", stats_after["pruned"] == [])
        check("idempotent no archive", stats_after["archive_bundled"] == 0)

        # 7. apply with restore-missing re-installs the missing skill at its category path.
        result_missing = core.apply(overwrite_modified=False, restore_missing=True)
        check("reinstall missing", result_missing["reinstalled"] == [missing_name],
              f"got {result_missing['reinstalled']}")
        reinstalled_dir = _find_skill_dir(missing_name)
        if reinstalled_dir is None:
            check(f"reinstall {missing_name} category", False, "still missing")
        elif reinstalled_dir.parent == skills_dir:
            check(f"reinstall {missing_name} category", False, "flat (category lost)")
        else:
            check(f"reinstall {missing_name} category", True)

        # 8. apply with overwrite reverts the edit.
        result_ow = core.apply(overwrite_modified=True)
        check("overwrite modified", result_ow["overwritten"] == [mod_name], f"got {result_ow['overwritten']}")
        mod_final = (_find_skill_dir(mod_name) / "SKILL.md").read_text(encoding="utf-8")
        check("edit reverted", "# local edit" not in mod_final)
        check("matches stock", _dir_hash(_find_skill_dir(mod_name)) == stock_hash)

    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] unexpected error: {exc!r}")
        failures.append("unexpected error")
    finally:
        reset_hermes_home_override(token)
        shutil.rmtree(home, ignore_errors=True)

    if failures:
        print(f"FAILED ({len(failures)}): {', '.join(failures)}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
