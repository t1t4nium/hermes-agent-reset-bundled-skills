# reset-bundled-skills

A Hermes Agent plugin that reinstalls bundled skills into their correct category
directories from the bundled source, in one command.

## What it does

`hermes reset-bundled-skills` restores every bundled skill that the curator archived,
placing each one back in its category directory (for example
`software-development/dogfood`, not a flat `dogfood/`). It also clears the two pieces of
bookkeeping that would otherwise make the skill invisible or keep it from re-seeding.

With `--overwrite-modified`, it additionally replaces bundled skills whose local copy was
edited (by the user or by the agent) with the stock version from the repo.

## Why

The curator, when `curator.prune_builtins` is enabled, archives bundled skills that stay
unused for a while. Two things happen to an archived skill:

1. Its directory moves to `~/.hermes/skills/.archive/`.
2. Its name is added to `~/.hermes/skills/.curator_suppressed`.

The built-in recovery commands do not handle this cleanly:

- `hermes curator restore <name>` moves the archived copy back, but to a flat path, so
  the category directory is lost.
- `hermes skills reset <name> --restore` re-copies from the bundled source with the
  category preserved, but the re-seeder skips any name still in `.curator_suppressed`, and
  the stale manifest entry makes the sync treat the skill as "deleted by the user". Doing
  it by hand requires clearing both files first, per skill.

This plugin does the whole job for all bundled skills at once, with a plan, a warning,
and a confirmation.

## What it touches

- `~/.hermes/skills/.curator_suppressed` - removes the pruned bundled skill names.
- `~/.hermes/skills/.archive/` - deletes the archived copies of bundled skills only.
  Optional and hub-installed skills in the archive are left untouched.
- `~/.hermes/skills/.bundled_manifest` - clears the entries for the reinstalled skills so
  the sync treats them as new.
- `~/.hermes/skills/` - re-copies each missing bundled skill at its category path via the
  built-in `sync_skills()`.
- `~/.hermes/skills/.usage.json` - drops the stale "archived" record for restored skills.

Active bundled skills that were never edited are left alone. Edited bundled skills are
only changed when `--overwrite-modified` is passed.

## Install

Install from Git (the official Hermes flow):

```bash
hermes plugins install t1t4nium/hermes-agent-reset-bundled-skills
```

Answer `y` to the `Enable now?` prompt, or pass `--enable`.

Verify it is loaded:

```bash
hermes plugins
```

The CLI command is available as `hermes reset-bundled-skills`. Run `hermes
reset-bundled-skills --help` to confirm.

## Usage

```text
hermes reset-bundled-skills status               # counters only, no changes
hermes reset-bundled-skills --dry-run            # print the plan, change nothing
hermes reset-bundled-skills                      # plan, warning, then confirmation
hermes reset-bundled-skills --yes                # skip the confirmation prompt
hermes reset-bundled-skills --overwrite-modified # also reset edited bundled skills
```

Options:

| Flag | Effect |
| --- | --- |
| `status` | Subcommand that prints counters and exits without changing anything. |
| `--dry-run` | Prints the plan and exits. No files change. |
| `--yes` | Runs without the interactive `[y/N]` prompt. |
| `--overwrite-modified` | Replaces bundled skills whose local copy differs from stock with the stock version. Destructive to local edits. |

Without `--yes`, the command always prints the plan and asks for confirmation before
touching anything. With `--overwrite-modified`, the confirmation warning is stronger.

## Example

```text
$ hermes reset-bundled-skills --dry-run
Plan
  restore 36 pruned bundled skill(s): arxiv, claude-code, codex, ...
  overwrite-modified: off (edited bundled skills are left as-is)
Dry run: no changes were made.
```

```text
$ hermes reset-bundled-skills status
Bundled skills
  tracked in manifest: 58
  pruned (in .curator_suppressed): 36
  modified (differ from stock): 0
Archive directory
  bundled entries: 36
  other entries (optional/hub, left untouched): 19
```

## How it works

The reset runs four steps, in order:

1. Remove the pruned names from `.curator_suppressed`.
2. Delete their directories under `.archive/`.
3. Clear their entries in `.bundled_manifest`.
4. Run the built-in `sync_skills()`, which copies every missing bundled skill back to its
   category path and rewrites the manifest.

When `--overwrite-modified` is set, the edited live copies are deleted before the sync, so
the sync re-copies the stock version.

## Self-test

The plugin ships a self-test for developers. It runs the whole recipe inside a
throwaway Hermes home and never touches the real profile: it seeds five pruned
bundled skills and one edited one, then exercises `status`, the plan, `apply`,
idempotency, and `--overwrite-modified`.

```bash
hermes reset-bundled-skills-selftest
```

Exit code 0 means everything passed. The skills are picked from the manifest at
runtime (essentials and protected built-ins excluded), so the test keeps working
as the bundled catalog changes.

A GitHub Actions workflow (`.github/workflows/compat.yml`) runs the same
self-test against the latest Hermes on a weekly schedule and on manual dispatch,
installing the plugin. It catches breakage introduced by Hermes updates without
any manual step.

## Notes and limitations

- Idempotent. Running it again after a successful reset reports nothing to do.
- Only bundled skills are touched. Optional and hub-installed skills, and any skill you
  wrote yourself, are never modified or deleted.
- The plugin calls Hermes internal modules (`tools.skills_sync`, `tools.skill_usage`).
  These are not a stable public API, so the plugin may need adjustment after a Hermes
  upgrade.
- After running, a session that is already open will not see the change until you reload
  skills (`/reload-skills`) or restart it.
- To keep the curator from re-archiving unused bundled skills later, set
  `curator.prune_builtins: false` in `config.yaml`. This plugin does not change that
  setting.
