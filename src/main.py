from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .gateway import router as gateway_router

# Load .env from the project root (FinSpark_Proto_v1/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI(
    title="FinSpark Integration Gateway",
    description="Middleware that reads JSON config blueprints and routes requests to external APIs",
    version="0.1.0",
)

# Allow CORS for the main app frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the gateway routes
app.include_router(gateway_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "middleware"}
