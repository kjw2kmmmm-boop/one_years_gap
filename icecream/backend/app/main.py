import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints.orders import order
from api.endpoints.measure import measure
from api.endpoints.dashboard import dashboard
from services.telemetry_service import telemetry_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await telemetry_service.start()
    try:
        yield
    finally:
        await telemetry_service.stop()


app = FastAPI(title="Icecream Cobot Backend", lifespan=lifespan)

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
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

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}