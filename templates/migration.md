# Migration prompt template

**From → To:** <e.g. MySQL → Postgres, callbacks → async/await, v2 → v3 API>

**Scope:** <which files / tables / modules / endpoints are in scope>

**What must stay identical:** <data, indexes, public behavior, response shapes>

**Compatibility:** <big-bang or incremental? must old + new coexist?>

**Risks / gotchas:** <known edge cases, data that won't map cleanly>

**Done when:** <migration script runs clean / parity tests pass / etc.>
