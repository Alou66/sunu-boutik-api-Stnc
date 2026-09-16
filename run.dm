.venv/bin/uvicorn app.main:app --reload --port 8000
source .venv/bin/activate
alembic upgrade head