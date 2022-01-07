"""
 Initializing some default parameters for api routes
"""

from fastapi import APIRouter

from .endpoints.tests import tests_router
from .endpoints.analytics import analytics_router

router = APIRouter()

router.include_router(tests_router, prefix="/tests")
router.include_router(analytics_router, prefix="/analytics")
