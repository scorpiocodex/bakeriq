import { useAuth } from '../context/AuthContext';

// Format today's date once per render. We don't memoize because it's
// cheap and the component re-renders rarely.
function formatToday() {
    return new Date().toLocaleDateString('en-IN', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });
}

// Greeting based on local hour — purely cosmetic but reinforces the
// "this app knows when you're using it" feeling.
function timeBasedGreeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
}

// User initials for the avatar circle. Falls back to '?' if no name.
function getInitials(fullName, email) {
    const source = fullName?.trim() || email?.split('@')[0] || '';
    if (!source) return '?';
    const parts = source.split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function TopBar() {
    const { user, logout } = useAuth();
    const greeting = timeBasedGreeting();
    const date = formatToday();
    const initials = getInitials(user?.full_name, user?.email);
    const firstName = user?.full_name?.split(' ')[0] || '';

    return (
        <header className="flex items-center justify-between mb-3">
            <div>
                <p className="text-sm font-medium text-slate-900">
                    {greeting}{firstName ? `, ${firstName}` : ''}
                </p>
                <p className="text-xs text-slate-500">{date} · Today's overview</p>
            </div>
            <div className="flex items-center gap-2">
                {/* Live indicator. In Phase 1 it's hard-coded green; in Phase 2 it
            reflects WebSocket connection state. */}
                <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded-full font-medium">
                    ● Live
                </span>
                {/* Avatar with click-to-logout via menu (Phase 1: just clickable). */}
                <button
                    onClick={logout}
                    title="Click to log out"
                    className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 text-xs font-medium flex items-center justify-center hover:bg-blue-200 transition-colors"
                >
                    {initials}
                </button>
            </div>
        </header>
    );
}