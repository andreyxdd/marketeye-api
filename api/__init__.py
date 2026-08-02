"""
 Initializing some default parameters for api routes
"""

from fastapi import APIRouter

from .endpoints.analytics import analytics_router
from .endpoints.scrapes import scrapes_router
from .endpoints.notifications import notifications_router
from .endpoints.tests import tests_router

router = APIRouter()

router.include_router(analytics_router, prefix="/analytics")
router.include_router(scrapes_router, prefix="/scrapes")
# ponytail: bounce HTTP API disabled (legacy app); keep api/endpoints/bounce.py + db/crud/bounce.py if re-enable needed
router.include_router(notifications_router, prefix="/notifications")
router.include_router(tests_router, prefix="/tests")
