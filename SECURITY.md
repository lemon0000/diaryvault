# Security

DiaryVault is designed for private diary data. The public repository should contain code, tests, scripts, and documentation only.

Do not commit:

- `DiaryVault/` — local diary archive, Markdown exports, images, SQLite database, logs, backups.
- `.secrets/` — Nideriji credentials, API tokens, tunnel profiles, runtime keys.
- `.tools/` — local tunnel binaries and downloaded helper tools.
- `.venv/` — local Python virtual environment.
- `.codex/` and `.vscode/` — machine-specific editor and MCP client configuration.

The MCP and REST APIs are read-only for diary content. They intentionally do not expose delete, update, SQL execution, command execution, or arbitrary file-read tools.

For ChatGPT web or other remote access, use HTTPS plus strong authentication. Rotate any token that was pasted into the wrong place or exposed in logs.
