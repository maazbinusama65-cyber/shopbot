# ShopBot test-session format

Test questions for the Leaf sales agent. One session (a conversation of 1 to 6 customer turns) per line in a `.jsonl` file.
Real examples: `harness/data/example_sessions.jsonl`. Check a file with:

```bash
python -m harness.validate_sessions contrib/G29.jsonl --contrib
```

## Document ids (`harness/corpus/`)

| Kind | Id | Example |
| --- | --- | --- |
| Product (price history, stock) | `PROD-<NAME>` | `PROD-WOOL-SCARF` |
| Shop policy | `POLICY-<NAME>` | `POLICY-RETURNS`, `POLICY-SHIPPING` |
| Promotion | `PROMO-<NAME>` | `PROMO-BLACK-FRIDAY` |

The corpus mirrors the seeded shop data in `backend/app/seed.py` (products, dated prices, policies, promo). Gold dates assume today is 2026-11-24.

## Session fields

`session_id` (`G29-T3-01`), `type` (T1 to T5), `author` (group id), `turns` (list of `{"user": text, "gold": record or null}`).
Only turns with a `gold` record are marked.

Gold record: `answer`, `answer_keywords` (1 to 4 words/numbers every correct answer contains; `"a|b"` for alternatives),
`citations` (doc ids), `exact_version` (false), `abstain`, `memory_dependent`, `depends_on_turns`, `as_of` (YYYY-MM-DD or null),
`evidence` (`{doc_id, quote}`; the quote must be copied word for word from the corpus, 20+ characters).

## Types

| Type | Tests | Rule |
| --- | --- | --- |
| T1 Current fact | today's price / stock, cited | 1+ citation and keywords |
| T2 Past price | the price on a past date (timeline), cited | cite the product, `as_of` set |
| T3 Multi-turn | uses a customer fact from an earlier turn (budget, size, ...) | 2+ turns, a `memory_dependent` gold turn |
| T4 Change history | what a policy/price changed from and to, and when | 2+ turns, memory dependent, year among keywords |
| T5 Should refuse | the shop data cannot answer it | every gold turn `abstain: true` |

For memory questions put the key fact at least 3 turns before the question that needs it.
