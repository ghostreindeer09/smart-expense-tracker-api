# AI_NOTES.md

I used Claude to scaffold this project from a detailed prompt covering the
stack, required endpoints, storage behavior, and edge cases. I worked in
stages — models, then storage, then routes, then tests, then README —
reviewing and running each stage before moving on, rather than accepting a
single large generated dump.

## 1. What was AI-generated vs. written by me

**AI-generated, reviewed and kept largely as-is:**
- `src/models.py` — Pydantic v2 schemas and field validation (including the
  `not_blank` validator on title/category and the `round_to_cents` validator
  on amount).
- `src/storage.py` — the in-memory dict store, JSON-file persistence, the
  atomic write (temp file + `os.replace`), and the lock around mutations.
- `src/main.py` — FastAPI routes and the exception handling for validation
  errors.
- `tests/test_expenses.py` — the pytest suite structure and all 35 test
  cases, including the parametrized bad-input cases and the non-finite-float
  (`NaN`/`Infinity`) handling.

**Written or fixed by me, after manual testing surfaced a bug:**
- **Fixed a real bug in the AI-generated validation-error handler.** See
  section 2 below — this was the single most significant thing I changed,
  and it came from testing, not code review.
- README wording and the curl examples — ran each one myself against a
  live server and fixed field names/paths that didn't match the actual
  code.

## 2. What I validated, tested, or changed, and why

- **Ran the exact README commands on a clean checkout.** Deleted my venv,
  recreated it, ran `pip install -r requirements.txt`, started the server
  with `uvicorn src.main:app --reload`, hit it with each curl example in
  order (create, list, filter, totals, delete), then ran `pytest -q` — all
  before finalizing the README, since these commands are meant to be run
  verbatim.

- **Validation errors crashed with 500 instead of returning 422.** This
  was the significant find. The AI-generated custom exception handler for
  `RequestValidationError` in `main.py` referenced
  `status.HTTP_422_UNPROCESSABLE_CONTENT` — a constant that doesn't exist
  in the installed Starlette version (only `HTTP_422_UNPROCESSABLE_ENTITY`
  does). So the handler itself threw an `AttributeError` every time it
  ran, meaning *every* invalid request — bad amount, bad date, blank
  title — crashed with a generic 500 instead of the intended 422 with
  field-level detail. I found this by manually testing edge cases via
  `/docs` before running the automated suite: amount = 0, amount = -5, an
  impossible date like `2026-02-30`, an empty title, and a whitespace-only
  title all came back 500. I confirmed the root cause from the server
  traceback (`AttributeError: module 'starlette.status' has no attribute
  'HTTP_422_UNPROCESSABLE_CONTENT'`), fixed it by switching to
  `HTTP_422_UNPROCESSABLE_ENTITY`, and reverified all five cases — each
  now correctly returns 422 with the specific field-level error (e.g.
  `greater_than` / "Input should be greater than 0" for the amount cases,
  `date_from_datetime_parsing` for the bad date, `string_too_short` and my
  own `value_error` message for the blank-title cases). I also found a
  sixth case by accident — a malformed JSON body (two objects pasted
  back-to-back in the Swagger UI) — which now correctly returns 422 with a
  `json_invalid` / "JSON decode error" detail instead of crashing,
  confirming the fix holds for FastAPI's body-parsing layer too, not just
  Pydantic's field validators.

  The underlying validation logic itself (the `gt=0` constraint on
  amount, the blank-string check, Pydantic's date parsing) was correct
  from the start — the bug was purely in how the error got reported back
  to the client. To double check whether my own test suite would have
  caught this, I later checked out the pre-fix version of `main.py` and
  ran `pytest` against it directly: **19 of 35 tests failed**, each with
  the real `AttributeError` traceback, not a silent pass. So the test
  suite's exact-status-code assertions (`assert resp.status_code == 422`)
  do their job correctly — the real gap was in my own workflow, not test
  coverage: I found this bug by testing manually via `/docs` before ever
  running the automated suite, when running `pytest` first would have
  surfaced it immediately with zero manual effort. See the limitations
  section for what I'm taking from that.

- **Rounding to 2 decimal places.** Added two expenses with amounts 0.10
  and 0.20 and checked `/expenses/total` — it returned a clean `0.3`, not
  a float-drifted value like `0.30000000000000004`. Rounding happens in
  the `round_to_cents` field validator on `ExpenseCreate.amount` in
  `models.py`, so it's rounded once at write time; the total then sums
  already-rounded values.

- **Empty-state totals.** Confirmed `/expenses/total` and
  `/expenses/total/by-category` return `0.0` and an empty breakdown
  respectively when no expenses exist, rather than erroring, per the
  assignment spec.

- **Category case-insensitivity.** Checked that `?category=Food` and
  `?category=FOOD` return identical results.

- **Persistence across restart.** Started the server, added a couple of
  expenses, killed the process, restarted it, and confirmed `GET
  /expenses` still returned them.

- **`EXPENSE_DATA_FILE` override.** Set the env var to
  `/tmp/does-not-exist-yet/expenses.json` (a directory that didn't exist)
  and started the server. It did not error — it created the directory
  automatically and wrote the file successfully. I confirmed this was
  actually a freshly-started server bound to the new path (had to kill a
  stale process on port 8000 first, since my first attempt at this test
  silently hit an old server instance instead — worth noting for anyone
  repeating this test, the "Address already in use" error is easy to miss
  and will make the test give a false result).

- **Delete behavior.** Confirmed deleting a valid id returns success and
  the expense no longer appears in `GET /expenses`, and that deleting a
  nonexistent or already-deleted id returns 404.

- **Full pytest suite: 35 passed against the fixed code, 1 unrelated
  warning** (a `PendingDeprecationWarning` from inside Starlette's own
  multipart-parsing dependency, not from my code or tests).

## 3. AI suggestions I decided not to use, and why

- Claude suggested switching to SQLite for persistence instead of the
  JSON file, citing better crash-safety. The assignment explicitly says
  no database is required, and the JSON file with atomic writes
  (temp file + `os.replace`) already covers the crash-safety concern at
  this scale, so I kept the simpler approach.
- It suggested adding a background thread to periodically flush to disk
  instead of writing on every mutation. For a personal expense tracker
  with low write volume, writing synchronously on every mutation is
  simpler to reason about and avoids a whole class of lost-write bugs on
  crash, so I declined the added complexity.
- It proposed a `PUT /expenses/{id}` update endpoint "for completeness."
  Left it out — outside the assignment's required scope, and I didn't
  want to add an untested, unrequested surface area.

## Known limitations / things I'd flag to a reviewer

- **The test suite would have caught the 500-vs-422 bug immediately, but
  I didn't run it before manually finding the issue.** I discovered the
  bug by testing edge cases by hand via `/docs` first, then ran `pytest`
  afterward (against the already-fixed code, so it passed). To check
  whether the suite itself was actually adequate, I later checked out the
  pre-fix version of `main.py` and ran the suite against it specifically:
  19 of 35 tests failed with the real traceback. So the gap wasn't in
  test coverage — the exact-status-code assertions correctly pin down
  422, not just "any failure" — the gap was in my own workflow. I should
  run the full suite first, before any manual testing, since it would
  have surfaced this in seconds instead of requiring manual edge-case
  testing via Swagger.
- The full-file rewrite on every mutation is O(n) per write; this is an
  intentional simplification appropriate at this scale, not an oversight.
- No concurrent-request stress testing beyond confirming the lock exists
  in `storage.py` — I trust it conceptually but didn't load-test it.
- No pagination on `GET /expenses`.
- I haven't specifically tested what happens if `data/expenses.json`
  becomes corrupted or malformed on disk while the server is stopped;
  `JsonFileStorage.load()` raises a hard `RuntimeError` in that case,
  which happens during FastAPI's `lifespan` startup — meaning a corrupted
  data file would currently crash the server on startup entirely rather
  than failing gracefully or recovering. This is a defensible
  fail-loudly design choice, but I haven't verified what the actual
  startup error looks like to a user.
