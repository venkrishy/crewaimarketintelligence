from fastapi import FastAPI

from crewinsight.api.routes import router
from crewinsight.telemetry import setup_telemetry

app = FastAPI(title="crewinsight", version="0.1.0")
setup_telemetry(app.title)
app.include_router(router)
