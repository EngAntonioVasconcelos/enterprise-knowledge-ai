

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from app.api.routes.invitations import (
    invitation_router,
    organization_router as organization_invitations_router,
)
from app.api.routes.organizations import router as organizations_router
from app.api.routes.users import router as users_router
from app.db.session import engine

from app.core.config import settings


app = FastAPI(
    title="Enterprise Knowledge AI",
    description=(
        "Enterprise AI Knowledge Assistant powered by RAG, LLMs and AI Agents."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(organizations_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(organization_invitations_router, prefix="/api/v1")
app.include_router(invitation_router, prefix="/api/v1")


@app.get("/", tags=["General"])
async def root():
    return {
        "message": "Welcome to Enterprise Knowledge AI API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Legacy health endpoint retained for backward compatibility."""
    return {
        "status": "healthy",
        "service": "enterprise-knowledge-ai-api",
    }


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    return {
        "status": "alive",
        "service": "enterprise-knowledge-ai-api",
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ready",
            "service": "enterprise-knowledge-ai-api",
            "database": "available",
        }

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "enterprise-knowledge-ai-api",
                "database": "unavailable",
            },
        )
