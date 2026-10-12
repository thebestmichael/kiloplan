# kiloplan

Strength training and nutrition tracking for powerlifters, with an assistant that
answers questions about a lifter's own program and logs. The assistant's model picks
tools and words the answer; every number comes from code.

## What works today

- Upload a coach's program spreadsheet (.xlsx). It is parsed into blocks, weeks and
  rows, stored in SQLite, and shown with a data quality report.
- Ask the assistant what to load, for example: "I took 405 for 3 on squat in week 4 at
  RPE 9. I have squat for 2 at RPE 5. What weight should I take?" It finds the logged
  set, estimates the one-rep max, computes the load and names the set it used.
- e1RM (Epley, Brzycki, hybrid) and RPE-based target load calculator.

Planned: in-app workout logging, plate calculator, nutrition logging, dbt analytics.

## Run it

```sh
uv sync
uv run uvicorn kiloplan.api.main:app --reload    # API on :8000
cd frontend && npm install && npm run dev        # UI on :5173
```

The assistant needs a local model: install [Ollama](https://ollama.com), then
`ollama pull qwen2.5:7b`. Everything else works without it.

## Test

```sh
uv run pytest
uv run ruff check .
```

Tests use a scripted stand-in for the model, so no model has to be running.
