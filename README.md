# SignalStack

Backend (Python) and frontend (Vite + React + TypeScript) monorepo.

## Structure

- **backend/** – Python app (`app/main.py`, `scan.py`, `scoring.py`, `brightdata.py`, `models.py`)
- **frontend/** – Vite + React + TypeScript app

## Run locally

**Backend**

```bash
cd backend && pip install -r requirements.txt && python -m app.main
```

**Frontend**

```bash
cd frontend && npm install && npm run dev
```

Frontend dev server proxies `/api` to the backend (default port 8000).

## Docker

```bash
docker build -t signalstack .
docker run -p 8000:8000 signalstack
```

## License

MIT

## Host 
Hosted on Zeabur - https://fullstack-app.zeabur.app/ 