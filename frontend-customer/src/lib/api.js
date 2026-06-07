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
