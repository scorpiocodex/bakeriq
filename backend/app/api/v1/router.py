from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    auth,
    billing,
    cart,
    categories,
    customers,
    dashboard,
    default_orders,
    invoice,
    orders,
    products,
    register,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(cart.router)
api_router.include_router(customers.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(register.router)
api_router.include_router(billing.router)
api_router.include_router(invoice.router)
api_router.include_router(default_orders.router)
api_router.include_router(orders.router)
api_router.include_router(orders.prefill_router)
api_router.include_router(dashboard.router)
api_router.include_router(webhooks.router)
api_router.include_router(approvals.router)
