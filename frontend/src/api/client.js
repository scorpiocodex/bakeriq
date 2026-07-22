import axios from 'axios';

// The dashboard is served under /app (see vite.config.js `base` and the
// BrowserRouter basename in main.jsx). React Router handles that prefix
// for us, but the raw window.location calls below don't go through the
// router — so they need it spelled out.
const APP_BASENAME = '/app';
const LOGIN_PATH = `${APP_BASENAME}/login`;

// Single axios instance for the whole app.
// baseURL is RELATIVE — '/api/v1' — so:
//   • In dev: Vite's proxy in vite.config.js forwards to the api container.
//   • In prod: nginx will serve the React bundle and proxy /api/* to the api container.
//   The same code works in both, no env-var swap needed.
//
// Unaffected by the /app basename: the leading slash means these resolve
// against the origin root, not the app's base path.
const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  // 10 second timeout — anything slower than this on an internal LAN
  // is a backend problem we want to surface, not silently wait through.
  timeout: 10_000,
});

// Request interceptor: attach the JWT to every outgoing request.
// Why an interceptor instead of passing the token to every call:
//   1. We never forget — auth is automatic.
//   2. Refreshing the token only touches localStorage, not every component.
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('bakeriq_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor: catch 401s globally.
// When the API returns 401, it means the token is missing, expired, or
// invalid. We wipe it from localStorage and redirect to the login page.
// Without this, components have to handle 401 individually — which they
// always forget to do.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const onLoginPage = window.location.pathname === LOGIN_PATH;
      localStorage.removeItem('bakeriq_token');
      if (!onLoginPage) {
        // Use replace so Back doesn't return to the protected page.
        window.location.replace(LOGIN_PATH);
      }
    }
    return Promise.reject(error);
  },
);

export default client;
