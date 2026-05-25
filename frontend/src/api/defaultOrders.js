/**
 * API client for default order endpoints.
 *
 * Default orders are customer-scoped — they live under /customers/{id}/default-order.
 * There's no separate default-order ID in the URL; the customer owns exactly
 * one template (or none).
 */
import client from './client';

/**
 * GET /customers/{customerId}/default-order
 *
 * Returns the customer's template (parent + items, each item embedding its
 * product). Throws 404 if the customer has no template yet — callers should
 * catch this and treat it as "empty, show the add-items form."
 */
export async function getDefaultOrder(customerId) {
    const { data } = await client.get(`/customers/${customerId}/default-order`);
    return data;
}

/**
 * PUT /customers/{customerId}/default-order
 *
 * Create or replace the template. payload is the full desired state:
 *   { notes, is_active, items: [{ product_id, quantity }, ...] }
 * Items are replaced wholesale. Returns the saved template with embedded
 * products. Throws 422 if any product_id is invalid or inactive.
 */
export async function upsertDefaultOrder(customerId, payload) {
    const { data } = await client.put(
        `/customers/${customerId}/default-order`,
        payload,
    );
    return data;
}

/**
 * DELETE /customers/{customerId}/default-order
 *
 * Removes the template entirely (parent + items via cascade). 204 on success.
 * Throws 404 if the customer has no template.
 */
export async function deleteDefaultOrder(customerId) {
    await client.delete(`/customers/${customerId}/default-order`);
    // 204 No Content — nothing to return
}