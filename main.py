from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel
from api.webhooks import router as webhooks_router
from api.vendors import router as vendors_router
from api.tags import router as tags_router
from api.verify import router as verify_router
from api.analytics import router as analytics_router
from core.database import async_engine

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://printpuf-8adgz.ondigitalocean.app",
]

app = FastAPI(
    title="PrintPUF API",
    description="Tag generation, enrolment, verification, analytics, and vendor management.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    cors_origin = origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0]
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
    from sqlalchemy import text
    import models.user  # noqa: F401 — ensures User table is registered
    import models.product  # noqa: F401
    import models.scan_event  # noqa: F401
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        # Add vendor_id column if the table already existed without it
        await conn.execute(
            text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS vendor_id VARCHAR UNIQUE')
        )


api_router = APIRouter(prefix="/api")

api_router.include_router(webhooks_router)
api_router.include_router(vendors_router)
api_router.include_router(tags_router)
api_router.include_router(verify_router)
api_router.include_router(analytics_router)

app.include_router(api_router)
