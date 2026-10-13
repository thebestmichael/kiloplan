# KiloPlan

Powerlifting data platform: workout and nutrition logging, e1RM analytics,
4-week block programming from lifter feedback, and an assistant that answers a
lifter's questions about their own uploaded program.
Portfolio project aimed at data engineering roles.

## Stack
- Python 3.12, pandas, FastAPI, pytest, ruff
- Frontend: React + TypeScript (Vite) in frontend/
- App database: SQLite via SQLAlchemy (data/kiloplan.db, gitignored)
- Assistant: local model through Ollama with tool calling, behind the ChatModel
  interface in src/kiloplan/chatbot/llm.py
- Warehouse: Snowflake. Transformations: dbt (SQL)
- Orchestration: Airflow or Dagster. Storage: S3 (Parquet)
- Infra: Terraform, Docker. CI: GitHub Actions

## Conventions
- Store all weights in kg. Convert only at the display layer.
- Type hints on all calculation code. Tests for every formula.
- SQL transformations go in dbt. Python handles API calls, progression
  logic, and the chatbot.
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

## Commands
- Install deps / create .venv: `uv sync`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Start API (port 8000): `uv run uvicorn kiloplan.api.main:app --reload`
- Start frontend (port 5173, proxies /api to the API): `cd frontend && npm run dev`
- Frontend lint / build: `cd frontend && npm run lint`, `npm run build`
- Assistant model: `ollama serve`, then `ollama pull qwen2.5:7b` once. Change the
  model with KILOPLAN_LLM_MODEL. Tests use ScriptedModel and need no model running.

(fill in as they exist: dbt build)