from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.ops import router as ops_router
from app.core.logging import configure_logging
from app.core.metrics import metrics

configure_logging()

app = FastAPI(title='JobSpy Async API', version='0.3.0')
app.include_router(jobs_router)
app.include_router(admin_router)
app.include_router(ops_router)


@app.get('/healthz')
def healthz() -> dict:
    return {'ok': True}


@app.get('/metrics')
def get_metrics() -> dict:
    return metrics.snapshot()


@app.get('/openapi.json', include_in_schema=False)
def openapi_artifact() -> dict:
    return app.openapi()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    # Pydantic v2 may embed non-serializable objects (e.g. ValueError) inside
    # error context dicts. Stringify them before passing to JSONResponse.
    def _serialisable_errors(errors: list) -> list:
        result = []
        for err in errors:
            entry = dict(err)
            if 'ctx' in entry and isinstance(entry['ctx'], dict):
                entry['ctx'] = {k: str(v) for k, v in entry['ctx'].items()}
            result.append(entry)
        return result

    return JSONResponse(
        status_code=422,
        content={
            'error': {
                'code': 'validation_error',
                'message': 'Request validation failed',
                'details': _serialisable_errors(exc.errors()),
            }
        },
    )
