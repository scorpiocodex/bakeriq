import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Asset URL prefix. The dashboard is reachable two ways:
  //   • directly at localhost:5173/app/ during normal dev
  //   • via the FastAPI /app/* proxy at <ngrok>/app/ — which is how the
  //     owner reaches the approvals page from the WhatsApp notification
  //     card on their phone, since ngrok's free tier gives us one tunnel
  //
  // The proxy forwards paths verbatim, so Vite has to expect requests
  // under /app/. Without this, assets would be emitted at /assets/... and
  // 404 through the proxy. Mirrors frontend-customer's base='/web/'.
  //
  // Note: this means localhost:5173 (bare) no longer serves the app —
  // use localhost:5173/app/ in dev.
  base: '/app/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // Hosts that Vite accepts requests from:
    // - 'frontend' is the docker service name; the FastAPI /app proxy
    //   strips the original Host header, so httpx sets it from the
    //   target URL and Vite sees 'frontend'. Without this entry every
    //   proxied request is rejected with "Blocked request".
    // - 'localhost' for direct dev access at localhost:5173/app/
    // - '.ngrok-free.dev' (leading dot = suffix match) in case we ever
    //   point a tunnel straight at the dashboard
    allowedHosts: ['frontend', 'localhost', '.ngrok-free.dev', '.ngrok.app'],
    // WSL/Docker bind mounts don't reliably emit inotify events.
    // Polling is slower but actually works.
    watch: {
      usePolling: true,
      interval: 300,
    },
    // Proxy API calls to the backend container during dev.
    // Browser hits localhost:5173/api/v1/... → Vite forwards to http://api:8000/api/v1/...
    // Why a proxy instead of just calling the API directly:
    //   1. No CORS configuration needed in dev (request is same-origin from browser's POV).
    //   2. Frontend code uses relative URLs, identical in dev and prod (where nginx proxies).
    //   3. JWTs in localStorage don't bump into third-party-cookie issues.
    //
    // Unaffected by base: axios calls start with a leading slash, so
    // they resolve against the origin root, not the base path. Through
    // the FastAPI proxy they land on the api directly.
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
      },
    },
  },
});
