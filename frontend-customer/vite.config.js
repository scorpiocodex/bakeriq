import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Asset URL prefix. When the customer app is served via the FastAPI
  // /web/* proxy in dev (and via nginx /web/* in prod), Vite needs to
  // generate asset URLs like /web/assets/index.js, not /assets/index.js.
  base: '/web/',
  server: {
    // Hosts that Vite accepts requests from:
    // - 'frontend-customer' is the docker service name; FastAPI's proxy
    //   forwards requests with this Host header when reaching us
    // - '.ngrok-free.dev' (leading dot = suffix match) for direct ngrok
    //   access when we want it
    // - 'localhost' for direct dev access at localhost:5174
    allowedHosts: ['frontend-customer', 'localhost', '.ngrok-free.dev', '.ngrok.app'],
  },
});
