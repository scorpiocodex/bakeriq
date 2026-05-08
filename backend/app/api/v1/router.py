"""Mounts every v1 sub-router under /api/v1."""

from app.api.v1 import auth, categories, customers, products
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
