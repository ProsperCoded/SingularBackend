from fastapi import FastAPI, APIRouter
from api.webhooks import router as webhooks_router
from api.vendors import router as vendors_router
from api.schemas_preview import router as schemas_preview_router

app = FastAPI()

api_router = APIRouter(prefix="/api")


@api_router.get("/")
def hello():
    return {"Hello": "World"}


api_router.include_router(webhooks_router)
api_router.include_router(vendors_router)
api_router.include_router(schemas_preview_router)

app.include_router(api_router)
