# backend/api/main.py

"""
FastAPI Application - Cost Optimiser API

Learning: FastAPI Features
===========================
1. Auto validation (Pydantic schemas)
2. Auto documentation (Swagger UI at /docs)
3. Async support (handle many requests concurrently)
4. Dependency injection (database sessions, auth)
5. Type hints everywhere (better IDE support)
"""

from contextlib import asynccontextmanager  # Required for lifespan
from datetime import datetime

from backend.api import schemas
from backend.models.database import get_db, init_db
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text  # Needed for health check
from sqlalchemy.orm import Session

# ============================================================================
# LIFESPAN (Must be defined BEFORE 'app')
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Replaces the deprecated @app.on_event("startup")
    """
    print("🚀 Starting Cloud Cost Optimiser API...")

    # Initialize database tables
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")

    print("✅ API ready to accept requests")
    print("📚 API docs available at: http://localhost:8000/docs")

    yield  # Application runs here

    print("🛑 Shutting down API...")


# ============================================================================
# APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Cloud Cost Optimiser API",
    description="Identify and track AWS cost savings opportunities",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # Alternative docs
    lifespan=lifespan,  # Now this works because lifespan is defined above
)

# ============================================================================
# CORS CONFIGURATION
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Cloud Cost Optimiser API",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health_check(db: Session = Depends(get_db)):
    """Detailed health check with database connectivity."""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# IMPORT & INCLUDE ROUTE MODULES
# ============================================================================

# Import routes (make sure backend/api/routes folder exists with these files)
from backend.api.routes import dashboard, findings, scans

app.include_router(scans.router, prefix="/api/scans", tags=["Scans"])
app.include_router(findings.router, prefix="/api/findings", tags=["Findings"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

# ============================================================================
# ERROR HANDLERS
# ============================================================================


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "detail": f"The requested resource was not found",
        "path": str(request.url),
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {
        "error": "Internal Server Error",
        "detail": "An unexpected error occurred. Please try again later.",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Run with: python -m backend.api.main
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes (dev only)
        log_level="info",
    )
