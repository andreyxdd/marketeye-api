"""
 Initializing some default parameters for api routes
"""

from fastapi import APIRouter

from .endpoints.tests import tests_router

router = APIRouter()

router.include_router(tests_router, prefix="/tests")
