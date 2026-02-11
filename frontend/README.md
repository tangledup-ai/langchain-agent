# Agent Manager Frontend

React frontend for configuring and launching agents through `fastapi_server/front_apis.py`.

## Run

```bash
cd /home/smith/projects/work/langchain-agent/frontend
npm install
npm run dev
```

## API Base URL

By default, the app calls:

- `http://127.0.0.1:8001`

If your `front_apis.py` server runs elsewhere, set:

```bash
VITE_FRONT_API_BASE_URL=http://<host>:<port>
```

