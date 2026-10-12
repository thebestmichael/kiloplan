# KiloPlan

Strength training tracking (like Bar Is Loaded) plus nutrition tracking (like
MyFitnessPal), with an AI coaching assistant on top. The assistant is the
differentiator: it answers questions about the lifter's own program, logs and
nutrition using tools over structured data.
Portfolio project aimed at data engineering roles.

## Architecture principle
- Every feature stores structured data and exposes tools. New features add tools
  the assistant can call.
- Tools are registered, not wired in: a feature provides a tool group (a class
  with `tools()` and `instructions`, like ProgramTools) and it is passed to the
  Toolbox in src/kiloplan/chatbot/toolbox.py. assistant.py names no tools and
  needs no change for a new group. toolbox.py lists the result keys the
  assistant relies on (status, message, set, based_on, below_chart_range).
- The assistant's model never does arithmetic and only answers from tool results.
  Code checks that every number in an answer came from a tool result or the
  lifter's own words.
- Lifter and date are first-class in the schema: programs, performed sets and
  nutrition all key on them.
- RAG is only for unstructured text (coach notes, warm-up guidance), never for
  load questions.

## Stack
In use:
- Python 3.12, FastAPI, SQLAlchemy 2, openpyxl, pytest, ruff, uv
- Frontend: React + TypeScript (Vite) in frontend/
- App database: SQLite (data/kiloplan.db, gitignored). KILOPLAN_DATABASE_URL
  changes it; moving to Postgres is a connection-string change.
  Schema changes go through Alembic migrations in src/kiloplan/storage/migrations/;
  the API applies them on startup. Tests build tables straight from the models.
- Assistant: local model through Ollama with tool calling, behind the ChatModel
  interface in src/kiloplan/chatbot/llm.py. No paid APIs.
- CI: GitHub Actions on pull requests (ruff lint and format check, pytest,
  frontend lint and build)

Planned, nothing exists yet: pandas, dbt, Snowflake, Airflow or Dagster,
S3 (Parquet), Terraform, Docker.

## Layout
- src/kiloplan/analytics/e1rm.py: e1RM formulas and target load
- src/kiloplan/ingestion/: coach spreadsheet parser, lift classifier
- src/kiloplan/storage/: models, engine, migrations, program store
- src/kiloplan/chatbot/: tool registry, program tools, model interface, assistant
- src/kiloplan/api/main.py: FastAPI app
- tests/workbooks.py: builders for synthetic coach workbooks

## Conventions
- Program rows hold the prescription. What the lifter actually lifted lives in
  performed_sets (lifter, date, lift, variation, load in kg, RPE, source). A
  spreadsheet upload fills it and replaces only its own sets; in-app logging
  will write to the same table. The assistant's tools read performed_sets only.
- Store all weights in kg. Convert only at the display layer and in tool results.
- Type hints on all calculation code. Tests for every formula.
- SQL transformations go in dbt. Python handles API calls, progression logic and
  the assistant.
- Never commit secrets. Credentials live in .env (gitignored). The real coach
  spreadsheet (samplespreadsheet/) and data/ are gitignored and must be copied
  between machines by hand. Tests use synthetic workbooks only.
- Workflow: one feature branch and PR per task, small commits with one purpose
  each (feat, fix, test, docs), merge when CI is green.
- Tests and CI never need a model running: they use ScriptedModel. The live test
  is opt-in with KILOPLAN_LIVE_LLM=1.

## Assistant rules
- RPE below 6 is under the chart range. Reps in reserve is still used
  (RPE 5 = 5 in reserve), the result is flagged below_chart_range, and the
  answer must say it is less reliable.
- A set logged as "<5" is never used as a basis set. The assistant asks instead.
- Basis set when the lifter names none: same lift variation, most recent week
  that has one, heaviest set of that day with a numeric RPE of 6 or higher. The
  answer names the set used. If none qualifies, ask.
- Never swap in a different lift variation without asking.
- Missing, ambiguous or conflicting data: say so and ask, never guess.
- Pain or injury mentions: direct to a professional, no load advice, no model
  call.

## Phase 1 acceptance test
"I took 405 for 3 reps on squat in week 4 at RPE 9. Now I'm on week 1 of a new
block and have squat for 2 reps at RPE 5. What weight should I take?"
Expected: finds the logged set, e1RM 441.8 lb, target 368.2 lb (167.0 kg), names
the set, states the below-chart caveat. See tests/test_assistant.py.

## Roadmap (in order)
1. Program storage + Q&A assistant with tool calling (built; hardening in progress)
2. Workout logging and history per lifter
3. Plate calculator
4. Nutrition: USDA FoodData Central search, daily logging, macro totals
5. Assistant tools for nutrition and combined questions
6. Accounts, hosting, club member rollout

Not built: dbt models, weekly volume metrics, 4-week block generator, in-app
workout logging, plate calculator, nutrition (page is a placeholder), accounts,
hosting. The API uses a single lifter named "default" until accounts exist.

## Commands
- Install deps / create .venv: `uv sync`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Start API (port 8000): `uv run uvicorn kiloplan.api.main:app --reload`
- Start frontend (port 5173, proxies /api to the API): `cd frontend && npm run dev`
- Frontend lint / build: `cd frontend && npm run lint`, `npm run build`
- Assistant model: `ollama serve`, then `ollama pull qwen2.5:7b` once. Change the
  model with KILOPLAN_LLM_MODEL.
- Live model test: `KILOPLAN_LIVE_LLM=1 uv run pytest tests/test_assistant.py`

- New migration after changing models: `uv run alembic revision --autogenerate -m "what changed"`
- Apply migrations by hand: `uv run alembic upgrade head`

(fill in as they exist: dbt build)
