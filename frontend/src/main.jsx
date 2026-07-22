import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext.jsx';
import './index.css';

// React Query: shared cache for all server state.
// staleTime: how long a query result is considered "fresh" before refetch
//   on mount/focus. 30s is a sensible default for an internal dashboard.
// retry: 1 — try once on failure. The default of 3 is too noisy for users.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// The dashboard is served under /app — see `base` in vite.config.js for
// why. Router paths stay declared without the prefix ('/orders', not
// '/app/orders'); basename tells React Router to match against the URL
// with /app stripped, and to prepend it when generating links.
//
// Unconditional rather than sniffed from window.location: Vite's base
// means the bundle only ever loads under /app/, in dev and in prod.
const ROUTER_BASENAME = '/app';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={ROUTER_BASENAME}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
