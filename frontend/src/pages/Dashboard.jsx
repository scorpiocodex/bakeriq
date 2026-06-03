/* eslint-disable react/no-unescaped-entities */
/* eslint-disable react/react-in-jsx-scope */
/* eslint-disable react/prop-types */
/**
 * Dashboard — today's order-flow snapshot.
 *
 * Four stat cards (Pending / In progress / Revenue / Cancelled), the order
 * board grouped by status, and a reference row (active customers/products,
 * unavailable today). All real data from /dashboard/summary.
 */
import { useNavigate } from 'react-router-dom';

import { useDashboardSummary } from '../hooks/useDashboard';

import { formatINR } from '../lib/format';

const BOARD_COLUMNS = [
  { key: 'received', label: 'Received', accent: 'border-slate-300', dot: 'bg-slate-400' },
  { key: 'preparing', label: 'Preparing', accent: 'border-amber-300', dot: 'bg-amber-400' },
  { key: 'ready', label: 'Ready', accent: 'border-blue-300', dot: 'bg-blue-400' },
  { key: 'delivering', label: 'Delivering', accent: 'border-teal-300', dot: 'bg-teal-400' },
];

function StatCard({ label, value, sub, valueClass = 'text-slate-900' }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md hover:border-slate-300 transition-all">
      <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useDashboardSummary();

  if (isLoading) {
    return <p className="text-sm text-slate-500 py-8 text-center">Loading dashboard…</p>;
  }
  if (isError) {
    return (
      <p className="text-sm text-red-700 py-8 text-center">
        Could not load dashboard: {error?.message ?? 'unknown error'}
      </p>
    );
  }

  const s = data;

  return (
    <>
      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 mb-2.5">
        <StatCard
          label="Pending"
          value={s.pending}
          sub="awaiting prep"
          valueClass="text-amber-600"
        />
        <StatCard
          label="In progress"
          value={s.in_progress}
          sub="preparing · ready · delivering"
          valueClass="text-blue-600"
        />
        <StatCard
          label="Revenue today"
          value={formatINR(s.revenue_today)}
          sub={`${s.today_orders} order${s.today_orders === 1 ? '' : 's'} today`}
        />
        <StatCard
          label="Cancelled"
          value={s.cancelled_today}
          sub="today"
          valueClass={s.cancelled_today > 0 ? 'text-red-600' : 'text-slate-900'}
        />
      </div>

      {/* Order board */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-2.5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-medium text-slate-900">Today's order board</p>
          <p className="text-xs text-slate-500">{s.summary_date}</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {BOARD_COLUMNS.map((col) => {
            const cards = s.board[col.key] ?? [];
            return (
              <div key={col.key}>
                <div className="flex items-center gap-1.5 mb-2">
                  <span className={`w-2 h-2 rounded-full ${col.dot}`} />
                  <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                    {col.label}
                  </p>
                  <span className="text-xs text-slate-400">· {cards.length}</span>
                </div>

                <div className="space-y-1.5">
                  {cards.length === 0 ? (
                    <p className="text-xs text-slate-400 py-2">—</p>
                  ) : (
                    cards.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => navigate('/orders')}
                        className={`w-full text-left bg-white border ${col.accent} rounded-lg px-3 py-2 hover:bg-slate-50`}
                      >
                        <p className="text-sm font-medium text-slate-900">{c.customer_name}</p>
                        <p className="text-xs text-slate-600">{c.item_summary}</p>
                      </button>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Reference row — fills the space below the board */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        <StatCard label="Active customers" value={s.active_customers} />
        <StatCard label="Active products" value={s.active_products} />
        <StatCard
          label="Unavailable today"
          value={s.unavailable_products}
          sub="products marked off"
          valueClass={s.unavailable_products > 0 ? 'text-amber-600' : 'text-slate-900'}
        />
      </div>
    </>
  );
}
