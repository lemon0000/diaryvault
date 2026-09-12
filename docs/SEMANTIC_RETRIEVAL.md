# DiaryVault semantic retrieval

DiaryVault now has two retrieval layers:

- `chunk_vectors`: existing 512-d local n-gram lexical vectors.
- `chunk_semantic_vectors`: optional local semantic embedding vectors.

`recall` and MCP `recall_memories` use this behavior:

```text
semantic vectors absent or provider unavailable -> local-vector
semantic vectors present and provider reachable -> hybrid-vector
```

The existing lexical vectors are not overwritten.

## Storage

Semantic vectors are stored in the same SQLite database:

```text
DiaryVault\db\diaryvault.sqlite
```

Table:

```text
chunk_semantic_vectors
```

Key fields:

- `chunk_id`
- `provider`
- `model`
- `dim`
- `vector`
- `text_hash`
- `embedded_at`

The `text_hash` field lets DiaryVault detect changed chunks and avoid re-embedding unchanged text.

## Build semantic vectors

Default provider:

```text
ollama
```

Default model:

```text
bge-m3
```

Start Ollama and pull the model:

```powershell
ollama pull bge-m3
```

Then build semantic vectors:

```powershell
cd C:\path\to\Diary
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault
```

The command is incremental. Re-running it should embed only missing or changed chunks.

DiaryVault connects to Ollama loopback directly and bypasses system proxy variables for this request. This avoids local `127.0.0.1:11434` calls being sent through `HTTP_PROXY` / `HTTPS_PROXY`.

Useful options:

```powershell
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault --limit 20
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault --force
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault --json
```

If Ollama is temporarily unavailable:

```powershell
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault --skip-if-unavailable
```

## Recall modes

Default:

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault
```

Force lexical-only:

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault --semantic off
```

Require semantic vectors and fail if unavailable:

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault --semantic required
```

Tune the semantic threshold:

```powershell
$env:DIARYVAULT_SEMANTIC_MIN_SCORE = "0.25"
```

## Daily sync

`scripts\run-diaryvault-daily.ps1` now runs:

1. `diaryvault daily --days 14`
2. `diaryvault index`
3. `diaryvault semantic-index --skip-if-unavailable`
4. `diaryvault stats --write-report`
5. `diaryvault validate`

`diaryvault index` preserves existing semantic vectors when the chunk text hash is unchanged, so daily indexing does not force a full semantic rebuild.

## References

- Ollama embeddings API: <https://docs.ollama.com/api/embed>
- Ollama BGE-M3 model page: <https://ollama.com/library/bge-m3>
