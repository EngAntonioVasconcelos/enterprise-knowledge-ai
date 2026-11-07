
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.organizations import router as organizations_router
from app.api.routes.users import router as users_router


app = FastAPI(
    title="Enterprise Knowledge AI",
    description="Enterprise AI Knowledge Assistant powered by RAG, LLMs and AI Agents.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Register API routers.
app.include_router(
    organizations_router,
    prefix="/api/v1",
)
app.include_router(
    users_router, 
    prefix="/api/v1")
@app.get("/", tags=["General"])
async def root():
    return {
        "message": "Welcome to Enterprise Knowledge AI API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "enterprise-knowledge-ai-api",
    }
