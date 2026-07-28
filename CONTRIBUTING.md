# Contributing

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/seed.py --reset
```

## Before opening a pull request

```bash
cd backend
python -m ruff check app tests scripts       # must pass
python -m ruff format app tests scripts      # must be clean
pytest -q --cov=app --cov-fail-under=80      # must pass

cd ../frontend
npx tsc --noEmit
npm run build
```

## Conventions

- **Money is always `Decimal`.** Never let a `float` touch a monetary value —
  use the helpers in `app/utils/money.py` (`D`, `q`, `to_minor_units`) and wrap
  multi-step arithmetic in `money_context()`.
- **New monetary columns use the `Money` type** from `app/models/types.py`, not
  `Numeric`. SQLite silently truncates `NUMERIC` to a C double.
- **Every state change writes an audit entry.** Use `audit.record(...)` and let
  the caller control the commit.
- **Anything that changes a report's financial substance invalidates signatures.**
  If you add a field to `report_content_hash`, add a regression test for it.
- Public functions get type hints and a docstring explaining *why*, not *what*.
- Tests live next to the feature they cover and must be deterministic — no network,
  no wall-clock dependencies beyond `date.today()`.

## Commit messages

Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
