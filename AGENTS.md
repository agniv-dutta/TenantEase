# TenantEase Khata — standing rules

Every agent session must follow these rules.

1. All data is synthetic. Never add real names, phone numbers, or scraped data. Faker `en_IN` only.
2. Randomness is seeded (default seed 42) so every run is reproducible.
3. The risk model may only use information available at the as-of timestamp. Any change to
   features must keep the leakage test passing.
4. Do not use name, phone, property or locality, or message language as model features. Occupation
   type is allowed but must stay behind a config flag so an ablation can run.
5. The risk score is for scheduling reminders only. Never surface it as a decision about eviction,
   rent pricing, or tenant screening.
6. Frontend styling comes only from `frontend/src/styles/tokens.css`. Do not introduce new colors,
   fonts, radii, or shadows without asking.
7. Add type hints, docstrings on public functions, and a pytest test for every module.
8. Do not add dependencies without listing them in your reply.
9. UI copy rules: sentence case, plain verbs, no all-caps labels, no emoji, errors explain the fix.

## Commands

- `make setup` — install backend and frontend dependencies
- `make seed` — generate the synthetic SQLite database
- `make train` — build features and train the model
- `make eval` — write metrics, slices, model card
- `make api` — run the FastAPI server
- `make web` — run the Vite dev server
- `make test` — run backend pytest
- `make check` — ruff, pytest, tsc, frontend build
- `make demo` — seed, train, then run api and web
