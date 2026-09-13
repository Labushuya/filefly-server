import importlib.metadata
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.auth.router import router as auth_router
from app.files.router import router as files_router

try:
    __version__ = importlib.metadata.version("filefly-server")
except Exception:
    __version__ = "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="FileFly Server",
    description="Self-hosted file upload server for the FileFly Android app",
    version=__version__,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(files_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/version")
async def version():
    return {"version": __version__}
