from fastapi import FastAPI

from app.api.v1.jobs import router as jobs_router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title='JobSpy Async API', version='0.1.0')
app.include_router(jobs_router)


@app.get('/healthz')
def healthz() -> dict:
    return {'ok': True}
