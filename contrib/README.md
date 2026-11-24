# Group test questions

`G29.jsonl` holds our 10 test sessions (2 of each type T1 to T5), format in `harness/FORMAT.md`.
Every gold answer and quote was written from `backend/app/seed.py` and must be checked by a group member.

```bash
python -m harness.validate_sessions contrib/G29.jsonl --contrib
```

Only the group leader submits the file.
