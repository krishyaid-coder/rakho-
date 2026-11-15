# What `forget` can and cannot reach

Read this before treating `bhoolo` as a legal erasure.

## What it covers

`forget` removes a note from Rakho's **live** store: the row, its FTS entry, and its vector. That actor will not get it back from `nikaalo`.

Derived notes (`metadata.derived_from`) are marked `orphaned`. `nikaalo` will not serve them as trusted context. `dekho` still can.

After the delete, Rakho runs `PRAGMA wal_checkpoint(TRUNCATE)` and reports **requested** vs **completed** (frames reclaimed). Requesting is not the same as finishing.

## What it does not cover

- **WAL / freed pages.** If a reader is still open, the checkpoint can return busy. Old bytes may sit in `-wal` or unused pages until the checkpoint completes (or you `VACUUM`). A forensic read of the file in that window can recover the row. See SQLite WAL docs 2.2 and 6.
- **Backups, snapshots, replicas** taken before the forget. Rakho cannot reach those files. That is the operator's job.
- **Copies already recalled** into a model, a printout, or a log. Deleting the source does not un-send what already left.

GDPR-style erasure: `forget` is one step. Pair it with backup retention and context/log hygiene. Those copies are **documented, not tested**.

## The gate is not a trust certificate

Accepted is not trusted. The default gate has false positives and misses. Do not treat a stored note as verified.
