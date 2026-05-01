"""Mounts every v1 sub-router under /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)

# As we add more modules in later phases:
# from app.api.v1 import customers, orders, products
# api_router.include_router(customers.router)
# api_router.include_router(orders.router)
