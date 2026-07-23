/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */
/**
 * Shared date-range control for the billing pages.
 *
 * The range lives in the URL as query params rather than component
 * state, so drilling into a customer and hitting Back returns you to the
 * same range, and an invoice URL carries its context when shared.
 */
import { useSearchParams } from 'react-router-dom';

/**
 * Format as YYYY-MM-DD in *local* time.
 *
 * Not toISOString() — that converts to UTC first, so midnight on 1 July
 * IST becomes 18:30 on 30 June UTC and every preset silently starts a
 * day early, pulling the previous month's last day into the total.
 */
function isoDate(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** First of the current month through today — what the owner wants most often. */
function defaultRange() {
  const today = new Date();
  return {
    start: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    end: isoDate(today),
  };
}

/**
 * Reads the range from the URL, falling back to the current month.
 * Returns [range, setRange]; setRange writes back to the URL.
 */
export function useBillingRange() {
  const [searchParams, setSearchParams] = useSearchParams();
  const fallback = defaultRange();

  const range = {
    start: searchParams.get('start') || fallback.start,
    end: searchParams.get('end') || fallback.end,
  };

  function setRange(next) {
    setSearchParams({ ...range, ...next }, { replace: true });
  }

  return [range, setRange];
}

/** Quick presets — most billing questions are one of these. */
const PRESETS = [
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'last_7', label: 'Last 7 days' },
  { key: 'last_30', label: 'Last 30 days' },
];

function presetRange(key) {
  const today = new Date();
  switch (key) {
    case 'last_month': {
      const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      const last = new Date(today.getFullYear(), today.getMonth(), 0);
      return { start: isoDate(first), end: isoDate(last) };
    }
    case 'last_7': {
      const from = new Date(today);
      from.setDate(from.getDate() - 6);
      return { start: isoDate(from), end: isoDate(today) };
    }
    case 'last_30': {
      const from = new Date(today);
      from.setDate(from.getDate() - 29);
      return { start: isoDate(from), end: isoDate(today) };
    }
    case 'this_month':
    default:
      return defaultRange();
  }
}

export default function BillingRange({ range, onChange }) {
  const invalid = range.start > range.end;

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-2.5 mb-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {PRESETS.map((p) => {
          const preset = presetRange(p.key);
          const isActive = preset.start === range.start && preset.end === range.end;
          return (
            <button
              key={p.key}
              onClick={() => onChange(preset)}
              className={`text-xs px-3 py-1 rounded-full border ${
                isActive
                  ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {p.label}
            </button>
          );
        })}

        <div className="ml-auto flex items-center gap-2">
          <input
            type="date"
            value={range.start}
            max={range.end}
            onChange={(e) => onChange({ start: e.target.value })}
            className="text-xs px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
          />
          <span className="text-xs text-slate-400">to</span>
          <input
            type="date"
            value={range.end}
            min={range.start}
            onChange={(e) => onChange({ end: e.target.value })}
            className="text-xs px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
          />
        </div>
      </div>

      {invalid && (
        <p className="text-xs text-red-600 mt-2">Start date must be on or before the end date.</p>
      )}
    </div>
  );
}
