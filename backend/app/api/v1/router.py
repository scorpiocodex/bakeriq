from app.api.v1 import (
    auth,
    categories,
    customers,
    dashboard,
    default_orders,
    orders,
    products,
)
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(default_orders.router)
api_router.include_router(orders.router)
api_router.include_router(orders.prefill_router)
api_router.include_router(dashboard.router)
