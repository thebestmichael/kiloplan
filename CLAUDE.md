# KiloPlan

Powerlifting app with three parts: gym calculators (RPE load, plates, rep
maxes, points, meet attempts), a food diary with macro tracking, and an
assistant that answers a lifter's questions about their own uploaded program.
Portfolio project aimed at data engineering roles.

## Stack
- Python 3.12, pandas, FastAPI, pytest, ruff
- Frontend: React + TypeScript (Vite) in frontend/
- App database: SQLite via SQLAlchemy (data/kiloplan.db, gitignored)
- Food data: USDA FoodData Central SR Legacy, loaded into the app database
- Assistant: local model through Ollama with tool calling, behind the ChatModel
  interface in src/kiloplan/chatbot/llm.py
- Pipeline: app database -> Parquet (data/lake/raw) -> dbt models in a local
  DuckDB warehouse (data/warehouse.duckdb). All of data/ is gitignored.
- Planned, not built: S3 for the Parquet files and a Snowflake dbt target.
- CI: GitHub Actions

## Conventions
- Store all weights in kg. Convert only at the display layer.
- Type hints on all calculation code. Tests for every formula.
- SQL transformations go in dbt. Python handles API calls, progression
  logic, and the chatbot.
- The dbt project in dbt/ reads the raw Parquet files as sources and must stay
  portable SQL, so the same models can run on Snowflake. Formulas that exist in
  both Python and SQL (e1RM, volume) are checked against each other in
  tests/test_pipeline.py.
- The assistant's volume and macro tools read the dbt tables, so they are only as
  fresh as the last pipeline run, and every such answer says when that was.
  Account tables (users, sessions) are never exported.
- Never commit secrets. Credentials live in .env (gitignored).
- Small commits, one purpose each. Conventional prefixes: feat, fix, test, docs.
- Uploaded programs are stored as structured rows (lifter, block, week, day,
  lift, sets, reps, load in kg, RPE), never as text chunks.
- The assistant's LLM never does arithmetic. Every number in an answer comes from
  a tool in src/kiloplan/chatbot/tools.py, and the answer shows the logged set it
  used. RAG is only for unstructured text (coach notes, warm-up guidance), never
  for load questions.
- RPE below 6 is under the chart range: reps in reserve is still used, the result
  is flagged below_chart_range, and the answer must say so. A set logged as "<5"
  is never used as a basis set.
- If the data needed is missing, ambiguous or conflicts with the log, the
  assistant says so and asks; it does not guess.
- Pain or injury input must tell the user to see a professional, with no load
  advice.
- Accounts: passwords are hashed with Argon2; a login is a random token in an
  HttpOnly cookie, stored only as a hash. Whose data a request touches comes from
  that cookie (or the shared guest lifter), never from a parameter in the request.
  Set KILOPLAN_COOKIE_SECURE=1 wherever the app is served over HTTPS.
- Food nutrients are stored per 100 g. A diary entry copies its macros when it
  is logged, so later changes to a food never rewrite past days.
- Points formulas (Wilks, DOTS, IPF GL) follow OpenPowerlifting's coefficients.

## Commands
- Install deps / create .venv: `uv sync`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Start API (port 8000): `uv run uvicorn kiloplan.api.main:app --reload`
- Start frontend (port 5173, proxies /api to the API): `cd frontend && npm run dev`
- Frontend lint / build: `cd frontend && npm run lint`, `npm run build`
- Load USDA foods (once, downloads about 6 MB): `uv run python -m kiloplan.ingestion.usda`
- Run the pipeline (export to Parquet, then dbt build): `uv run python -m kiloplan.pipeline`
- dbt alone: `uv run dbt build --project-dir dbt --profiles-dir dbt`
- Assistant model: `ollama serve`, then `ollama pull qwen2.5:7b` once. Change the
  model with KILOPLAN_LLM_MODEL. Tests use ScriptedModel and need no model running.
