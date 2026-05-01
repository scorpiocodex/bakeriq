import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Wrap protected pages with <ProtectedRoute>:
 *   <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
 *     <Route index element={<Dashboard />} />
 *     ...
 *   </Route>
 *
 * Three states this component handles:
 *   1. Still loading (auth bootstrap in progress) — render a placeholder.
 *   2. Loaded, no user — redirect to /login, remember where they came from.
 *   3. Loaded, authenticated — render children.
 */
export default function ProtectedRoute({ children }) {
    const { user, loading } = useAuth();
    const location = useLocation();

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-100 flex items-center justify-center">
                <div className="text-slate-500 text-sm">Loading…</div>
            </div>
        );
    }

    if (!user) {
        // 'replace' swaps the current history entry instead of pushing a new
        // one. Without it: user types /dashboard → bounced to /login → logs
        // in → presses Back → returns to /dashboard which redirects again.
        // 'state' carries the originally-requested URL so we could return
        // them to it after login (we don't in Phase 1, but the wiring is here).
        return <Navigate to="/login" replace state={{ from: location }} />;
    }

    return children;
}