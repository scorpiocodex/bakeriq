import axios from 'axios';

// Same-origin API calls when served via the FastAPI /web proxy (prod-like).
// For dev access directly at localhost:5174, fall back to the explicit
// API base URL so the dev workflow without ngrok still works.

// Detect: are we being served from /web (proxy) or directly?
const isProxied = typeof window !== 'undefined' && window.location.pathname.startsWith('/web');

const baseURL = isProxied
  ? '' // same origin
  : import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function fetchCart(token) {
  const { data } = await api.get(`/api/v1/cart/${token}`);
  return data;
}

export async function saveCart(token, items) {
  const { data } = await api.post(`/api/v1/cart/${token}`, { items });
  return data;
}

export async function placeOrder(token, items) {
  const { data } = await api.post(`/api/v1/cart/${token}/place`, { items });
  return data;
}

/**
 * GET /api/v1/register/{token}
 * Returns { phone, already_registered } on success.
 * Throws on 404 (no token) / 410 (consumed or expired) / 409 (edge case).
 * Errors surface via axios error object with response.status and response.data.detail.
 */
export async function fetchRegistrationToken(token) {
  const { data } = await api.get(`/api/v1/register/${token}`);
  return data;
}

/**
 * POST /api/v1/register/{token}
 * Body: { name, address_line_1?, address_line_2?, city?, state?, pincode? }
 * Returns { message, registration_id } on 200.
 */
export async function submitRegistration(token, payload) {
  const { data } = await api.post(`/api/v1/register/${token}`, payload);
  return data;
}

/**
 * GET /api/v1/invoice/{token}
 *
 * Returns the customer's latest invoice — every order on the day of
 * their most recent one. Throws 404 if the token is expired, the wrong
 * kind, or the customer has never ordered.
 */
export async function fetchInvoice(token) {
  const { data } = await api.get(`/api/v1/invoice/${token}`);
  return data;
}
