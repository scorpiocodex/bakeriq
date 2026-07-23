/**
 * Inventory API — owner-only stock management.
 *
 * Stock exists only for sealed goods. Made-to-order items appear in the
 * prep list instead, which is derived from today's orders rather than
 * stored. See the backend inventory_service for why.
 */
import client from './client';

/** GET /inventory/stock → { items, total, low_stock_count } */
export async function listStock({ lowOnly = false } = {}) {
  const { data } = await client.get('/inventory/stock', {
    params: { low_only: lowOnly },
  });
  return data;
}

/**
 * GET /inventory/prep → { items, total, is_visible }
 *
 * is_visible marks the 5 AM - 9 PM window. Outside it the numbers are
 * either still moving or already history, so the page hides the section.
 */
export async function getPrepList() {
  const { data } = await client.get('/inventory/prep');
  return data;
}

/**
 * PATCH /inventory/stock/{id} — set an absolute count.
 *
 * Absolute rather than a delta: this is what the owner enters after
 * counting a shelf.
 */
export async function setStock(productId, quantity) {
  const { data } = await client.patch(`/inventory/stock/${productId}`, {
    quantity,
  });
  return data;
}

/** PATCH /inventory/settings/{id} — tracking on/off, threshold */
export async function updateStockSettings(productId, payload) {
  const { data } = await client.patch(`/inventory/settings/${productId}`, payload);
  return data;
}
