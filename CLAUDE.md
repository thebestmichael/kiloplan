# KiloPlan

Powerlifting data platform: workout and nutrition logging, e1RM analytics,
4-week block programming from lifter feedback, and a warm-up RAG chatbot.
Portfolio project aimed at data engineering roles.

## Stack
- Python 3.12, pandas, FastAPI, pytest, ruff
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
- The chatbot gives general warm-up guidance only. Pain or injury input
  must tell the user to see a professional.

## Commands
- Install deps / create .venv: `uv sync`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`

(fill in as they exist: dbt build, start API)