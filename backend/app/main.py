from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import clusters, jobs, health, credentials

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RKE2 Automation API", version="0.1.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(credentials.router, prefix="/api/credentials", tags=["credentials"])
app.include_router(clusters.router, prefix="/api/clusters", tags=["clusters"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
