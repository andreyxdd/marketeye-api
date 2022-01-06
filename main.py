"""
MarketEye API v1
"""
import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from core.settings import DEFAULT_ROUTE_STR
from api import router as endpoint_router
from db.mongodb import close, connect

app = FastAPI(title="MarketEye API", version="1")

app.include_router(endpoint_router, prefix=DEFAULT_ROUTE_STR)


@app.on_event("startup")
async def on_app_start():
    """Anything that needs to be done while app starts"""
    await connect()


@app.on_event("shutdown")
async def on_app_shutdown():
    """Anything that needs to be done while app shutdown"""
    await close()


@app.get("/")
async def home():
    """Home page"""
    return Response("MarketEye API v1")


if __name__ == "__main__":
    uvicorn.run(app, log_level="debug", reload=True)
