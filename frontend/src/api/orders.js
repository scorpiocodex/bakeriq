/**
 * API client for order endpoints.
 *
 * Orders are first-class resources (not customer-scoped like default orders),
 * EXCEPT the prefill helper which reads a customer's default template.
 *
 * List returns compact rows (item_count, no items); detail returns the full
 * order with line items. Status changes go through a dedicated PATCH.
 */
import client from './client';

/**
 * GET /orders — compact list, newest first, with optional filters.
 *
 * filters: { skip, limit, status, customerId, orderDate }
 *   status:     one of received|preparing|ready|delivering|cancelled
 *   customerId: restrict to one customer
 *   orderDate:  YYYY-MM-DD, restrict to one day
 *
 * Returns { items, total, skip, limit }. Each item is a compact row
 * (customer summary, status, date, total_amount, item_count) — no line items.
 */
export async function listOrders({
    skip = 0,
    limit = 50,
    status = null,
    customerId = null,
    orderDate = null,
} = {}) {
    const params = { skip, limit };
    if (status) params.status = status;
    if (customerId) params.customer_id = customerId;
    if (orderDate) params.order_date = orderDate;

    const { data } = await client.get('/orders', { params });
    return data;
}

/**
 * GET /orders/{id} — full order detail with line items + customer summary.
 */
export async function getOrder(id) {
    const { data } = await client.get(`/orders/${id}`);
    return data;
}

/**
 * POST /orders — create a new order.
 *
 * payload: {
 *   customer_id, order_date?, status?, notes?,
 *   items: [{ product_id, quantity }, ...]   // at least one
 * }
 * Items are snapshotted server-side. Returns the full created order.
 * Throws 404 if customer missing, 422 if a product is invalid/inactive
 * or items is empty.
 */
export async function createOrder(payload) {
    const { data } = await client.post('/orders', payload);
    return data;
}

/**
 * PUT /orders/{id} — edit date/notes and optionally replace items.
 *
 * payload: any subset of { order_date, notes, items }
 * If items is provided it replaces all lines (re-snapshotted, total
 * recomputed). Status is NOT changed here — use changeOrderStatus.
 */
export async function updateOrder(id, payload) {
    const { data } = await client.put(`/orders/${id}`, payload);
    return data;
}

/**
 * PATCH /orders/{id}/status — move the order to a new status.
 *
 * Allowed: forward/back within the lifecycle, cancel from any state.
 * Throws 422 trying to reactivate a cancelled order.
 * Returns the full updated order.
 */
export async function changeOrderStatus(id, status) {
    const { data } = await client.patch(`/orders/${id}/status`, { status });
    return data;
}

/**
 * DELETE /orders/{id} — hard-delete an order (items cascade).
 * Prefer cancelling for real orders; delete is for genuine mistakes.
 */
export async function deleteOrder(id) {
    await client.delete(`/orders/${id}`);
    // 204 No Content
}

/**
 * GET /customers/{customerId}/order-prefill — suggested order lines from
 * the customer's default order template.
 *
 * Returns { items: [{ product_id, product_name, unit_price, unit_label,
 * quantity }], skipped_count }. Inactive template products are skipped;
 * skipped_count tells the UI how many were dropped. Empty items if the
 * customer has no template. Prices are current product prices.
 */
export async function getOrderPrefill(customerId) {
    const { data } = await client.get(`/customers/${customerId}/order-prefill`);
    return data;
}