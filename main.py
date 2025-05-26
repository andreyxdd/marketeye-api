"""
MarketEye API v1
"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from core.settings import DEFAULT_ROUTE_STR
from api import router as endpoint_router
from db.mongodb import connect as connect_mongo, close as close_mongo
from db.redis import connect as connect_redis

VERSION = "1.5.0"

tags_metadata = [
    {
        "name": "Home",
        "description": "Initial endpoint.",
    },
    {
        "name": "Analytics",
        "description": "Endpoints to read computed indicators or sorted lists of tickers.",
    },
    {
        "name": "Scrapes",
        "description": "Endpoints to read web-scraping results.",
    },
    {
        "name": "Notifications",
        "description": "Endpoints to report issues.",
    },
    {
        "name": "Bounce",
        "description": "Endpoints to read data processed with bounce algorithm.",
    },
    {
        "name": "Tests",
        "description": "Some endpoints for internal tests",
    },
]

app = FastAPI(
    docs_url=None,
    title="Market-Eye API",
    version=VERSION,
    # pylint: disable=C0301
    description="**Market-Eye API** provides methods for computing technical indicators of individual stocks (_e.g. MACD, EMAs, MFI, etc._) as well as indicators describing the market as a whole (_e.g. CVI, VIX, etc._). The EOD (end of the day) historical data is fetched from Nasdaq Data Link API. The only markets analyzed are _NASDAQ_ and _NYSE_. The API also includes a scraping bot that collects the number of mentions of a given stock ticker. The scraping is done across some of the most popular news websites. Finally, the API provides methods for sorting all the stock data and scraping results (for the given date) based on several implemented criteria.",
    contact={
        "name": "Andrei Volkov",
        "email": "volkov@ualberta.ca",
    },
    license_info={
        "name": "GPL-3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
    openapi_tags=tags_metadata,
)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")
app.include_router(endpoint_router, prefix=DEFAULT_ROUTE_STR)


@app.on_event("startup")
async def on_app_start():
    """Anything that needs to be done while app starts"""
    await connect_mongo()
    await connect_redis()


@app.on_event("shutdown")
async def on_app_shutdown():
    """Anything that needs to be done while app shutdown"""
    await close_mongo()


@app.get("/", tags=["Home"], response_class=HTMLResponse)
async def market_eye_api(request: Request):
    """Initial endpoint"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "version": VERSION,
        },
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Adding favicon"""
    return FileResponse("/assets/icon.ico")


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    """Adding favicon to swagger ui docs endpoint"""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Market-Eye API",
        swagger_favicon_url="/assets/icon.ico",
    )


if __name__ == "__main__":
    uvicorn.run(app, log_level="debug", reload=True)
