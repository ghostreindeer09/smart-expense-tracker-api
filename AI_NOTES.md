# AI_NOTES.md

I used Claude to scaffold this project from a detailed prompt covering the
stack, required endpoints, storage behavior, and edge cases. I worked in
stages — models, then storage, then routes, then tests, then README —
reviewing and running each stage before moving on, rather than accepting a
single large generated dump.

## 1. What was AI-generated vs. written by me

**AI-generated, reviewed and kept largely as-is:**
- `src/models.py` — Pydantic v2 schemas and field validation.
- `src/storage.py` — the in-memory dict store, JSON-file persistence, the
  atomic write (temp file + `os.replace`), and the lock around mutations.
- `src/main.py` — FastAPI routes and the 422 handling for validation errors.
- `tests/test_expenses.py` — the pytest suite structure and most test cases.


- README wording and the curl examples — ran each one myself against a
  live server and fixed field names/paths that didn't match the actual
  code.


## 2. What I validated, tested, or changed, and why

- **Ran the exact README commands on a clean checkout.** Deleted my venv,
  recreated it, ran `pip install -r requirements.txt`, started the server
  with `uvicorn src.main:app --reload`, hit it with each curl example in
  order (create, list, filter, totals, delete), then ran `pytest -q` — all
  before finalizing the README, since these commands are meant to be run
  verbatim. [Note anything you had to fix — e.g. a dependency missing from
  requirements.txt, a typo in a curl path.]

- **Rounding to 2 decimal places.** I specifically tested that
  `/expenses/total` doesn't drift from floating-point summation — e.g.
  adding several amounts like `0.1 + 0.2` style values and checking the
  total still comes back as a clean 2-decimal number rather than something
  like `0.30000000000000004`. [Fill in what you actually found — did the
  generated code round on the way in, on the way out, or both? Did you
  have to change that?]

- **Empty-state totals.** Confirmed `/expenses/total` and
  `/expenses/total/by-category` return `0.0` and an empty breakdown
  respectively when no expenses exist, rather than erroring, per the
  assignment spec.

- **Category case-insensitivity.** Checked that `?category=Food` and
  `?category=FOOD` return identical results, and that the `by-category`
  breakdown groups differently-cased duplicates into a single bucket
  rather than creating separate entries — I verified this was actually
  the behavior rather than assuming it from the code.

- **Persistence across restart.** Started the server, added a couple of
  expenses, killed the process, restarted it, and confirmed `GET
  /expenses` still returned them — i.e. that the load-on-startup path
  actually reads what the mutation path wrote.

- **`EXPENSE_DATA_FILE` override.** Set the env var to a scratch path
  before starting the server and confirmed data was written there instead
  of the default `data/expenses.json`, and that the app doesn't silently
  fall back to the default if the custom path's directory doesn't exist.


- **Atomic write behavior.** I didn't fuzz-test this (e.g. by killing the
  process mid-write), but I read through the temp-file + `os.replace`
  logic to confirm it wouldn't leave `expenses.json` half-written or
  corrupted on a crash, since that's the whole point of using `os.replace`
  over an in-place write. 

- **Validation edge cases.** Added my own cases beyond what was
  auto-generated, tried by hand via `/docs`: [e.g. "amount of exactly
  0 (should be rejected since spec says positive)", "a negative amount",
  "a syntactically valid but nonexistent date like 2026-02-30", "an empty
  title / a title that's only whitespace"]. [Fill in what you actually
  tried and what came back.]

- **Delete behavior.** Confirmed deleting a valid id returns success and
  the expense no longer appears in `GET /expenses`, and that deleting a
  nonexistent or already-deleted id returns `404` rather than a silent
  success.

## 3. AI suggestions I decided not to use, and why

- [Fill in: e.g. "Claude suggested switching to SQLite via `sqlite3` for
  persistence instead of the JSON file, citing better crash-safety. The
  assignment explicitly says no database is required, and the JSON file
  with atomic writes already covers the crash-safety concern at this
  scale, so I kept the simpler approach."]
- [Fill in: e.g. "It suggested adding a background thread to periodically
  flush to disk instead of writing on every mutation. For a personal
  expense tracker with low write volume, writing synchronously on every
  mutation is simpler to reason about and avoids a whole class of
  lost-write bugs on crash, so I declined the added complexity."]
- [Fill in: e.g. "It proposed a `PUT /expenses/{id}` update endpoint 'for
  completeness.' Left it out — outside the assignment's required scope,
  and I didn't want to add an untested, unrequested surface area."]
- [Add anything else you rejected, including bonus features you
  considered (search, monthly summary, Docker) and didn't build.]

## Known limitations / things I'd flag to a reviewer

- [Optional, honest gaps — e.g. "The full-file rewrite on every mutation
  is O(n); documented in the README as an intentional simplification, not
  an oversight, since it's fine at this scale." "No concurrent-request
  stress testing beyond the lock existing — I trust it conceptually but
  didn't load-test it." "No pagination on GET /expenses."]
