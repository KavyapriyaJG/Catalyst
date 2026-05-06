from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from api.routes.epic_routes import router as epic_router
from api.routes.story_routes import router as story_router
from api.routes.prd_routes import router as prd_router
from api.routes.file_routes import router as file_router
from api.routes.backlog_routes import router as backlog_router

_settings = get_settings()

# Ensure required directories exist on startup
_settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_settings.GENERATED_PRDS_DIR.mkdir(parents=True, exist_ok=True)
_settings.BACKLOG_FILES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(epic_router)
app.include_router(story_router)
app.include_router(prd_router)
app.include_router(file_router)
app.include_router(backlog_router)
