# Ponytail coding-agent guidance

This project includes `AGENTS.md`, a project-level version of Ponytail's coding guidance. Compatible agents that read `AGENTS.md` can use it without installing a separate plugin.

The full Ponytail plugin is a separate install for a supported coding agent. It is not a plugin that can be loaded into an ordinary ChatGPT browser conversation or into the Python project itself.

Official repository and install guide:
- https://github.com/DietrichGebert/ponytail
- https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md

For Codex CLI, the official installation guide currently documents these as separate commands:

```powershell
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

Then start Codex, review and trust its two lifecycle hooks in `/hooks`, and start a new thread. Only run these commands if Codex CLI is installed and you intend to use that agent. Do not run them in the AutoClips Python virtual environment as application dependencies; Ponytail is an optional coding-agent tool.

The project-level `AGENTS.md` is included as the practical setup for tools that read repository instructions. It does not install the full plugin commands or hooks.
