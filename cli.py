"""CLI surface for the reset-bundled-skills plugin."""

from __future__ import annotations

import argparse
from typing import Any, Dict


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and exit without changing anything.",
    )
    subparser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    subparser.add_argument(
        "--overwrite-modified",
        action="store_true",
        help=(
            "Also replace bundled skills whose local copy was edited (by the user or the "
            "agent) with the stock bundled version."
        ),
    )
    subparser.add_argument(
        "--restore-missing",
        action="store_true",
        help=(
            "Also re-install bundled skills whose manifest entry lingered after their "
            "directory disappeared (the 'user-deleted' state the sync refuses to re-add). "
            "Use with caution: a skill may have been deleted on purpose."
        ),
    )
    subs = subparser.add_subparsers(dest="action")
    subs.add_parser("status", help="Show counters without changing anything.")
    subparser.set_defaults(func=reset_bundled_skills_command)


def reset_bundled_skills_command(args: argparse.Namespace) -> int:
    from . import core

    if getattr(args, "action", None) == "status":
        return _print_status(core.status())
    return _run(args, core)


def _print_status(stats: Dict[str, Any]) -> int:
    print("Bundled skills")
    print(f"  tracked in manifest: {stats['bundled_total']}")
    print(f"  pruned (in .curator_suppressed): {len(stats['pruned'])}")
    print(f"  modified (differ from stock): {len(stats['modified'])}")
    print(f"  missing (manifest entry, no directory): {len(stats['missing'])}")
    if stats["missing"]:
        print(f"    -> {', '.join(stats['missing'])}")
    print("Archive directory")
    print(f"  bundled entries: {stats['archive_bundled']}")
    print(f"  other entries (optional/hub, left untouched): {stats['archive_other']}")
    return 0


def _run(args: argparse.Namespace, core: Any) -> int:
    overwrite = bool(args.overwrite_modified)
    restore_missing = bool(args.restore_missing)
    plan = core.collect_plan(overwrite_modified=overwrite, restore_missing=restore_missing)
    pruned = plan["pruned"]
    modified = plan["modified"]
    missing = plan["missing"]

    print("Plan")
    print(f"  restore {len(pruned)} pruned bundled skill(s): {', '.join(pruned) if pruned else 'none'}")
    if overwrite:
        print(f"  overwrite {len(modified)} modified bundled skill(s): {', '.join(modified) if modified else 'none'}")
    else:
        print("  overwrite-modified: off (edited bundled skills are left as-is)")
    if restore_missing:
        print(f"  re-install {len(missing)} missing bundled skill(s): {', '.join(missing) if missing else 'none'}")
    else:
        print("  restore-missing: off (user-deleted bundled skills are left as-is)")

    if not pruned and not modified and not missing:
        print("Nothing to do.")
        return 0

    if args.dry_run:
        print("Dry run: no changes were made.")
        return 0

    if not args.yes and not _confirm(overwrite, restore_missing):
        print("Aborted.")
        return 1

    result = core.apply(overwrite_modified=overwrite, restore_missing=restore_missing)
    print("Done.")
    print(f"  restored: {len(result['restored'])}")
    print(f"  overwritten: {len(result['overwritten'])}")
    print(f"  re-installed: {len(result['reinstalled'])}")
    print(f"  archive entries removed: {len(result['archive_removed'])}")
    print(f"  copied by final sync: {len(result['copied'])}")
    print(f"  updated by final sync: {len(result['updated'])}")
    if result["user_modified"]:
        print(f"  still user-modified (kept): {', '.join(result['user_modified'])}")
    return 0


def _confirm(overwrite: bool, restore_missing: bool = False) -> bool:
    if overwrite:
        print(
            "\nWARNING: --overwrite-modified will discard local edits to bundled skills "
            "and replace them with the stock versions. This cannot be undone."
        )
    if restore_missing:
        print(
            "\nWARNING: --restore-missing will re-install bundled skills that have no "
            "directory on disk. If you deleted one of them on purpose, it will come back."
        )
    answer = input("Proceed? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def register_selftest_cli(subparser: argparse.ArgumentParser) -> None:
    subparser.set_defaults(func=selftest_command)


def selftest_command(args: argparse.Namespace) -> int:
    from . import selftest

    return selftest.run()
