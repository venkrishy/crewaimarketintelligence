from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crewinsight.api.routes import router
from crewinsight.telemetry import setup_telemetry

app = FastAPI(title="crewinsight", version="0.1.0")

setup_telemetry(app.title)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://crew-insight.theaiguru.dev", "https://theaiguru.dev"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
