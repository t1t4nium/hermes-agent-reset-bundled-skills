"""Reset bundled skills to a clean, category-correct state.

Operator-facing CLI only. The plugin registers two commands and exposes no
model-facing tools:

- ``hermes reset-bundled-skills`` — the operator command.
- ``hermes reset-bundled-skills-selftest`` — the developer self-test.
"""

from __future__ import annotations

from .cli import (
    register_cli,
    register_selftest_cli,
    reset_bundled_skills_command,
    selftest_command,
)


def register(ctx) -> None:
    ctx.register_cli_command(
        name="reset-bundled-skills",
        help="Reinstall bundled skills into their category directories",
        setup_fn=register_cli,
        handler_fn=reset_bundled_skills_command,
        description=(
            "Reinstalls bundled skills that the curator archived, placing each back in "
            "its category directory from the bundled source. Can also overwrite bundled "
            "skills whose local copy was edited."
        ),
    )
    ctx.register_cli_command(
        name="reset-bundled-skills-selftest",
        help="Run the plugin self-test",
        setup_fn=register_selftest_cli,
        handler_fn=selftest_command,
        description=(
            "Runs the reset-bundled-skills self-test in an isolated temporary home. "
            "Developer-facing; exits non-zero on failure."
        ),
    )
