# MotionCare Development

## Stack

- Backend: Django + Django REST Framework
- Database: PostgreSQL
- Task broker: Redis + Celery
- Frontend: React + TypeScript + Ant Design

## Local Startup

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo Login

- Phone: `13800000000`
- Password: `pass123456`

