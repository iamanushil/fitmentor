# FitMentor Backend

See the top-level [ROADMAP.md](../ROADMAP.md) for the full 2-week build plan.

## Quick start (Day 1)

```bash
cp .env.example .env
docker compose up -d postgres redis
poetry install
poetry run uvicorn fitmentor.main:app --reload --app-dir src

curl http://localhost:8000/api/v1/health
# {"status":"ok"}
```

## Next steps

Work through `ROADMAP.md` day by day. Each day ends with something you can demo — don't skip ahead.
