from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from api.webhooks import router as webhooks_router
from api.vendors import router as vendors_router
from api.tags import router as tags_router
from api.verify import router as verify_router
from api.analytics import router as analytics_router

app = FastAPI(
    title="PrintPUF API",
    description="Tag generation, enrolment, verification, analytics, and vendor management.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://printpuf-8adgz.ondigitalocean.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

api_router.include_router(webhooks_router)
api_router.include_router(vendors_router)
api_router.include_router(tags_router)
api_router.include_router(verify_router)
api_router.include_router(analytics_router)

app.include_router(api_router)
