import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 5173,
        strictPort: true,
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
        proxy: {
            '/api': {
                target: 'http://api:8000',
                changeOrigin: true,
            },
        },
    },
});