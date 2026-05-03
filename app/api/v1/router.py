"""app/api/v1/router.py — Aggregates all v1 sub-routers."""

from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.integrations import router as integrations_router
from app.api.v1.endpoints.repositories import router as repositories_router
from app.api.v1.endpoints.users import router as users_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(integrations_router)
api_v1_router.include_router(repositories_router)
api_v1_router.include_router(users_router)
