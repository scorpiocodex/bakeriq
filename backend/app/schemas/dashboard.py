"""Dashboard summary schema — the shape of GET /dashboard/summary.

A single read-only snapshot for the owner's morning glance. Everything is
computed from existing data (orders, customers, products) — no new tables.

Contract for the frontend:
  today_orders        — total orders with order_date == today
  pending             — today's orders in 'received' status (need action)
  in_progress         — today's orders in preparing/ready/delivering
  cancelled_today     — today's orders in 'cancelled'
  revenue_today       — sum of today's non-cancelled order totals
  board               — today's non-cancelled orders grouped by status,
                        each a compact card for the order board
  active_customers    — reference count
  active_products     — reference count
  unavailable_products— active products NOT available today (heads-up)
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class BoardOrderCard(BaseModel):
    """One order on the board — minimal info to render a card + click through."""

    id: UUID
    customer_name: str
    item_summary: str  # e.g. "10 puffs · 5 ladoo" (built server-side)
    status: str


class DashboardSummary(BaseModel):
    # Today's order-flow headline numbers
    today_orders: int
    pending: int
    in_progress: int
    cancelled_today: int
    revenue_today: float

    # The order board — today's active orders grouped by status
    board: dict[str, list[BoardOrderCard]]  # keyed by status

    # Reference counts (the secondary row that fills the space)
    active_customers: int
    active_products: int
    unavailable_products: int

    # Echo back which day this summary is for
    summary_date: date
