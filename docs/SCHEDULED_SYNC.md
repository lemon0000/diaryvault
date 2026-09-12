# DiaryVault scheduled sync

Recommended setup: keep the full archive as the base, then run a small daily refresh.

Daily command:

```powershell
.\.venv\Scripts\python.exe -m diaryvault daily --vault .\DiaryVault --mode mine --days 14 --secrets-file .\.secrets\nideriji.env
```

What it does:

- fetches current sync metadata from nideriji.cn;
- refreshes only diary entries whose diary date is within the last 14 days;
- merges refreshed entries into `DiaryVault\raw\archive.json`;
- rewrites Markdown files under `DiaryVault\entries`;
- reuses existing images and downloads only newly referenced images;
- writes `DiaryVault\raw\daily-report.json`;
- can be followed by `diaryvault validate`.

The 14-day window is intentional. It handles normal late edits without doing a full 1535-entry content fetch every night. If you edit an older diary, run either:

```powershell
.\.venv\Scripts\python.exe -m diaryvault daily --vault .\DiaryVault --mode mine --days 90 --secrets-file .\.secrets\nideriji.env
```

or a full sync:

```powershell
.\.venv\Scripts\python.exe -m diaryvault sync --vault .\DiaryVault --mode mine --secrets-file .\.secrets\nideriji.env
```

Two helper scripts are provided:

- `scripts\run-diaryvault-daily.ps1` runs daily sync, rebuilds the SQLite index, refreshes semantic vectors when Ollama is available, refreshes stats reports, validates the vault, then writes a timestamped log to `DiaryVault\logs`.
- `scripts\register-diaryvault-daily-task.ps1` registers a Windows Scheduled Task named `DiaryVault Daily Sync`, defaulting to 03:00 local time.

Register the 03:00 task manually:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-diaryvault-daily-task.ps1
```

Register a different time:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-diaryvault-daily-task.ps1 -At 04:30
```

Check task status:

```powershell
Get-ScheduledTask -TaskName "DiaryVault Daily Sync"
Get-ScheduledTaskInfo -TaskName "DiaryVault Daily Sync"
```

Run the task immediately:

```powershell
Start-ScheduledTask -TaskName "DiaryVault Daily Sync"
```
