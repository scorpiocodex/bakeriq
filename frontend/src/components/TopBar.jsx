/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */
import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Route → subtitle map. The TopBar's small grey caption changes with the
 * current page rather than always saying "Today's overview" (which only
 * made sense on the Dashboard).
 */
const ROUTE_SUBTITLES = {
  '/': "Today's overview",
  '/orders': 'Manage and track customer orders',
  '/customers': 'Manage your customer list',
  '/products': 'Manage your product catalog',
  '/inventory': 'Stock levels and ingredient pool',
  '/billing': 'Receipts, invoices, and payments',
  '/settings': 'Configure BakeriQ for your bakery',
};

const DEFAULT_SUBTITLE = "Today's overview";

function formatToday(date) {
  return date.toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function formatTime(date) {
  return date.toLocaleTimeString('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function timeBasedGreeting(date) {
  const h = date.getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

/**
 * Hook that returns a Date that re-renders every minute. We only display
 * hour:minute precision so a 1-minute tick is enough — no need to update
 * every second.
 *
 * Alignment trick: the first interval fires at the next exact minute
 * boundary, not 60s after mount. This means "11:23" → "11:24" flips
 * within ~1s of the actual minute change, not whenever the page happened
 * to load.
 */
function useCurrentTime() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    // ms until the next minute boundary
    const msToNextMinute = 60_000 - (Date.now() % 60_000);

    let interval;
    const timeout = setTimeout(() => {
      setNow(new Date());
      interval = setInterval(() => setNow(new Date()), 60_000);
    }, msToNextMinute);

    return () => {
      clearTimeout(timeout);
      if (interval) clearInterval(interval);
    };
  }, []);

  return now;
}

export default function TopBar({ onMenuClick }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const now = useCurrentTime();

  const greeting = timeBasedGreeting(now);
  const date = formatToday(now);
  const time = formatTime(now);
  const firstName = user?.full_name?.split(' ')[0] || '';
  const subtitle = ROUTE_SUBTITLES[pathname] ?? DEFAULT_SUBTITLE;

  return (
    <header className="flex items-center justify-between gap-3 mb-3">
      {/* Left cluster: hamburger (mobile only) + greeting */}
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          onClick={onMenuClick}
          className="lg:hidden p-1.5 -ml-1 text-slate-600 hover:bg-slate-200 rounded-md"
          aria-label="Open navigation menu"
        >
          <Menu size={20} />
        </button>
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900 truncate">
            {greeting}
            {firstName ? `, ${firstName}` : ''}
          </p>
          <p className="text-xs text-slate-600 truncate">
            {date} · {subtitle}
          </p>
        </div>
      </div>

      {/* Right cluster: live time + Live indicator. No avatar — identity
                lives in the sidebar footer. */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="hidden sm:inline text-xs text-slate-600 font-mono">{time}</span>
        <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded-full font-medium">
          ● Live
        </span>
      </div>
    </header>
  );
}
