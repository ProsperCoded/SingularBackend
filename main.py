from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.auth import router as auth_router
from api.vendors import router as vendors_router
from api.tags import router as tags_router
from api.verify import router as verify_router
from api.analytics import router as analytics_router
from core.config import settings
from core.database import async_engine
from core.schema import ensure_schema

app = FastAPI(
    title="PrintPUF API",
    description="Tag generation, enrolment, verification, analytics, and vendor management.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://singular-frontend-beta.vercel.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    cors_origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Credentials": "true",
        },
    )


@app.on_event("startup")
async def on_startup():
    if settings.SYNC_DATABASE:
        await ensure_schema(async_engine)


api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(vendors_router)
api_router.include_router(tags_router)
api_router.include_router(verify_router)
api_router.include_router(analytics_router)

app.include_router(api_router)
