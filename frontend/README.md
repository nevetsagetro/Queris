# Queris frontend

React + TypeScript + Vite client for the Queris FastAPI service.

Run the API against the larger local demo database:

```bash
QUERIS_DATABASE=data/online_retail.duckdb queris-api
```

Then run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` when the API is not on `http://localhost:8000`.

The client exposes the 100 curated examples from `GET /examples`, schema discovery from
`GET /catalog`, query results from `POST /query`, and browser-session history. The API remains the
authority for SQL validation, execution, and query caching; the browser never executes SQL.
