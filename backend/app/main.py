from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers tables)
from app.config import get_settings
from app.database import Base, engine
from app.routers import auth, catalog, chat, errors, interview, kb

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Phase 1: create tables on startup. Later we switch to Alembic migrations.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SAP Copilot AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(kb.router)
app.include_router(catalog.router)
app.include_router(interview.router)
app.include_router(errors.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "sap-copilot-ai"}
