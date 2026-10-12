# KiloPlan frontend

React + TypeScript app built with Vite.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the FastAPI server on port 8000
npm run lint
npm run build
```

The API must be running for the calculator to work. From the repo root:

```bash
uv run uvicorn kiloplan.api.main:app --reload
```
