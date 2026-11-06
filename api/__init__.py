"""
 Initializing some default parameters for api routes
"""

from fastapi import APIRouter

from .endpoints.analytics import analytics_router
from .endpoints.scrapes import scrapes_router
from .endpoints.notifications import notifications_router
from .endpoints.tests import tests_router
from .endpoints.stock_bounce import stock_bounce_router, stock_bounce_v2_router

router = APIRouter()

router.include_router(analytics_router, prefix="/analytics")
router.include_router(scrapes_router, prefix="/scrapes")
router.include_router(stock_bounce_router, prefix="/stock-bounce/v1")
router.include_router(stock_bounce_v2_router, prefix="/stock-bounce/v2")
router.include_router(notifications_router, prefix="/notifications")
router.include_router(tests_router, prefix="/tests")
