# Caveman (vendored)

Caveman v4.0.1 from https://github.com/JuliusBrussee/caveman (Apache-2.0, see `LICENSE`).

Cloud sessions don't install Claude Code plugins, so the plugin's pieces are committed here instead:

- `.claude/skills/` — caveman, ultracave, megacave, cavecrew, caveman-commit, caveman-review, caveman-compress, caveman-help, caveman-stats, and the work-pattern skills
- `.claude/agents/` — cavecrew investigator, builder, reviewer
- `.claude/caveman/hooks/` — the plugin's hook scripts, registered in `.claude/settings.json`

The hooks turn caveman on at session start, hand it to subagents, and track `/caveman <mode>` and "stop caveman". `CLAUDE_PLUGIN_ROOT` points them at `.claude/` so they read the mode rules from `.claude/skills/<mode>/SKILL.md`. The statusline nudge is pre-dismissed because cloud sessions have no statusline.

To update, copy the same files from a newer release tag.
