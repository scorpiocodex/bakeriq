/**
 * Customer API calls.
 *
 * Every function returns the parsed response data (or throws on error).
 * The axios instance in client.js handles JWT injection and 401 redirects,
 * so these functions stay focused on the per-endpoint shape.
 *
 * Pattern: one function per endpoint, named consistently as
 * listX / getX / createX / updateX / deactivateX. Tomorrow's products.js
 * will follow this same template — copy, paste, change names.
 */
import client from './client';

/**
 * GET /customers — paginated, filterable list.
 *
 * Returns: { items, total, skip, limit }
 *
 * Why we build params manually instead of passing the whole filter object:
 * axios serialises {search: null} as ?search= (empty string), which the
 * backend would interpret as "name contains empty string" — matching every
 * row. Omitting null params entirely is the cleaner contract.
 */
export async function listCustomers({
    skip = 0,
    limit = 50,
    search = null,
    whatsappOnly = null,
    includeInactive = false,
} = {}) {
    const params = { skip, limit, include_inactive: includeInactive };
    if (search) params.search = search;
    if (whatsappOnly !== null) params.whatsapp_only = whatsappOnly;

    const { data } = await client.get('/customers', { params });
    return data;
}

/**
 * GET /customers/{id}
 */
export async function getCustomer(customerId) {
    const { data } = await client.get(`/customers/${customerId}`);
    return data;
}

/**
 * POST /customers
 *
 * payload shape:
 * {
 *   name, primary_phone, secondary_phone, preferred_channel_phone,
 *   whatsapp_enabled, address, notes
 * }
 *
 * Backend normalises phones (strips whitespace), so the client can
 * send "+91 99999 12345" and the database stores "+919999912345".
 */
export async function createCustomer(payload) {
    const { data } = await client.post('/customers', payload);
    return data;
}

/**
 * PUT /customers/{id} — partial update; only fields you pass get changed.
 * Backend uses model_dump(exclude_unset=True) so unspecified fields stay.
 */
export async function updateCustomer(customerId, payload) {
    const { data } = await client.put(`/customers/${customerId}`, payload);
    return data;
}

/**
 * DELETE /customers/{id} — soft delete (sets is_active=false).
 * Returns the deactivated customer object so the UI can update without
 * a follow-up GET.
 */
export async function deactivateCustomer(customerId) {
    const { data } = await client.delete(`/customers/${customerId}`);
    return data;
}