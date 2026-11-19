import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints.orders import order
from api.endpoints.measure import measure
from api.endpoints.dashboard import dashboard
from api.endpoints.manual import manual
from db.database import init_db
from services.manual_control_service import ManualControlError, manual_control_service
from services.script_runner_service import script_runner_service
from services.telemetry_service import telemetry_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await telemetry_service.start()
    try:
        await manual_control_service.start()
    except ManualControlError:
        pass
    try:
        yield
    finally:
        await script_runner_service.stop_current(stop_robot=False)
        await manual_control_service.stop()
        await telemetry_service.stop()


app = FastAPI(title="Icecream Cobot Backend", lifespan=lifespan)

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(order)
app.include_router(measure)
app.include_router(dashboard)
app.include_router(manual)

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}