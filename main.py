from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.jobs import router as jobs_router
from app.core.logging import configure_logging
from app.core.metrics import metrics

configure_logging()

app = FastAPI(title='JobSpy Async API', version='0.2.0')
app.include_router(jobs_router)


@app.get('/healthz')
def healthz() -> dict:
    return {'ok': True}


@app.get('/metrics')
def get_metrics() -> dict:
    return metrics.snapshot()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            'error': {
                'code': 'validation_error',
                'message': 'Request validation failed',
                'details': exc.errors(),
            }
        },
    )
