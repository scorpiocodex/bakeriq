import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    // Where to send them after login. Defaults to '/'.
    const from = location.state?.from?.pathname || '/';

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);

    async function handleSubmit(e) {
        e.preventDefault();
        setError('');
        setSubmitting(true);
        try {
            await login(email, password);
            navigate(from, { replace: true });
        } catch (err) {
            // The API returns 401 with detail "Incorrect email or password".
            // We use a single generic message regardless of the exact reason
            // (matches the backend's anti-enumeration policy).
            setError('Incorrect email or password');
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
            <form
                onSubmit={handleSubmit}
                className="bg-white border border-slate-200 rounded-lg p-8 w-full max-w-sm"
            >
                {/* Logo + brand strip */}
                <div className="flex items-center gap-2.5 mb-6">
                    <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
                        <svg
                            width="20"
                            height="20"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="white"
                            strokeWidth="2.2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                            <line x1="3" y1="6" x2="21" y2="6" />
                            <path d="M16 10a4 4 0 0 1-8 0" />
                        </svg>
                    </div>
                    <div>
                        <p className="text-base font-medium text-slate-900 leading-tight">BakeriQ</p>
                        <p className="text-xs text-slate-500">Bakery operations platform</p>
                    </div>
                </div>

                {/* Heading */}
                <h2 className="text-lg font-medium text-slate-900 mb-1">Welcome back</h2>
                <p className="text-sm text-slate-500 mb-6">Sign in to manage today's orders</p>

                {/* Error banner */}
                {error && (
                    <div
                        role="alert"
                        className="bg-red-50 border border-red-200 text-red-800 text-sm px-3 py-2 rounded-lg mb-4"
                    >
                        {error}
                    </div>
                )}

                {/* Email */}
                <label htmlFor="email" className="block text-sm text-slate-700 mb-1.5">
                    Email address
                </label>
                <input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="owner@bakeriq.com"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 mb-4"
                />

                {/* Password */}
                <label htmlFor="password" className="block text-sm text-slate-700 mb-1.5">
                    Password
                </label>
                <input
                    id="password"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 mb-5"
                />

                {/* Submit */}
                <button
                    type="submit"
                    disabled={submitting}
                    className="w-full py-2.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg font-medium text-sm transition-colors"
                >
                    {submitting ? 'Signing in…' : 'Sign in'}
                </button>

                {/* Footer */}
                <div className="text-center mt-6 pt-4 border-t border-slate-200">
                    <p className="text-xs text-slate-500">
                        Need help? Contact{' '}
                        <span className="text-brand-600">admin@bakeriq.com</span>
                    </p>
                </div>
            </form>
        </div>
    );
}