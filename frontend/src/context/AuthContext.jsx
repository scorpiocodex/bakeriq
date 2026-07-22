import { createContext, useContext, useEffect, useState } from 'react';
import { login as apiLogin, getMe } from '../api/auth';

// Context = React's built-in dependency-injection mechanism.
// Anything wrapped in <AuthProvider> can read the value with useAuth().
// We don't use Redux/Zustand here because auth state is small (one user
// object + 3 functions) and accessed in only a handful of components.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    // 'loading' starts true so the app doesn't flash the login page while
    // we're still verifying the token from localStorage on mount.
    const [loading, setLoading] = useState(true);

    // Bootstrap effect: runs once on mount. If a token exists, call /me to
    // confirm it's still valid. If yes, populate user. If no, the response
    // interceptor in client.js cleared the bad token; we just stop loading.
    useEffect(() => {
        const token = localStorage.getItem('bakeriq_token');
        if (!token) {
            setLoading(false);
            return;
        }
        getMe()
            .then((me) => setUser(me))
            .catch(() => {
                // Interceptor already cleared the token + redirected if needed.
                // If we got here without redirect, the user wasn't on a protected
                // route, so just leave user=null.
            })
            .finally(() => setLoading(false));
    }, []);

    // Called by the Login page on form submit.
    async function login(email, password) {
        const { access_token } = await apiLogin(email, password);
        localStorage.setItem('bakeriq_token', access_token);
        const me = await getMe();
        setUser(me);
        return me;
    }

    function logout() {
        localStorage.removeItem('bakeriq_token');
        setUser(null);
        // Hard navigate so any cached query state is wiped.
        window.location.href = '/app/login';
    }

    const value = { user, loading, login, logout };
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Custom hook with a guard. If a developer forgets to wrap the tree in
// <AuthProvider>, useAuth() would silently return null and downstream
// `user.email` would throw a confusing error. The guard makes the bug
// loud and unambiguous.
export function useAuth() {
    const ctx = useContext(AuthContext);
    if (ctx === null) {
        throw new Error('useAuth must be used within <AuthProvider>');
    }
    return ctx;
}