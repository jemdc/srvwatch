"""
SRVWatch Central Server
-----------------------
- Hosts the REST API for the frontend
- Runs the background poller (APScheduler)
- Serves the static frontend from /frontend
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # load .env before anything else

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import poller
import cache
from db import init_db
from routers.health import router as health_router
from routers.metrics import router as metrics_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("srvwatch.central")

app = FastAPI(title="SRVWatch Central", version="1.0.0", docs_url="/api/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(health_router)
app.include_router(metrics_router)

# Serve the frontend as static files at /
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.on_event("startup")
async def startup():
    log.info("Initialising database...")
    await init_db()
    log.info("Starting poller...")
    poller.start_poller("servers.yaml")
    log.info("SRVWatch Central ready.")


@app.on_event("shutdown")
async def shutdown():
    poller.stop_poller()
    await cache.close_redis()
    log.info("SRVWatch Central stopped.")
