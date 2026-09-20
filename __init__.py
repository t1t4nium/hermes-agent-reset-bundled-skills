"""Reset bundled skills to a clean, category-correct state.

Operator-facing CLI only. The plugin registers a single ``hermes reset-bundled-skills``
command and exposes no model-facing tools.
"""

from __future__ import annotations

from .cli import register_cli, reset_bundled_skills_command


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
