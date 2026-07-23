/**
 * Billing API — read-only views over orders.
 *
 * All four take an inclusive date range. Omitting it lets the server
 * default to the current calendar month.
 */
import client from './client';

/** GET /billing/summary → { revenue, order_count, customer_count, cancelled_count } */
export async function getBillingSummary({ start, end }) {
  const { data } = await client.get('/billing/summary', { params: { start, end } });
  return data;
}

/** GET /billing/customers → { items, total } — customers with billable orders */
export async function listBillingCustomers({ start, end }) {
  const { data } = await client.get('/billing/customers', { params: { start, end } });
  return data;
}

/** GET /billing/customers/{id}/dates → { customer, items, total } */
export async function listCustomerInvoiceDates(customerId, { start, end }) {
  const { data } = await client.get(`/billing/customers/${customerId}/dates`, {
    params: { start, end },
  });
  return data;
}

/** GET /billing/customers/{id}/invoice/{date} → the invoice, or 404 */
export async function getInvoice(customerId, invoiceDate) {
  const { data } = await client.get(`/billing/customers/${customerId}/invoice/${invoiceDate}`);
  return data;
}
