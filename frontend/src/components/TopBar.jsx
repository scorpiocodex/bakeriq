import { Menu } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

function formatToday() {
  return new Date().toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function formatTime() {
  return new Date().toLocaleTimeString('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function timeBasedGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function TopBar({ onMenuClick }) {
  const { user } = useAuth();
  const greeting = timeBasedGreeting();
  const date = formatToday();
  const time = formatTime();
  const firstName = user?.full_name?.split(' ')[0] || '';

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
          <p className="text-xs text-slate-500 truncate">{date} · Today's overview</p>
        </div>
      </div>

      {/* Right cluster: date/time + Live indicator. No avatar — identity
                now lives in the sidebar footer. */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="hidden sm:inline text-xs text-slate-500 font-mono">{time}</span>
        <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded-full font-medium">
          ● Live
        </span>
      </div>
    </header>
  );
}
