/* eslint-disable react/react-in-jsx-scope */
/**
 * Billing — level 1 of the drill-down.
 *
 *   /billing                          summary + customers        <- this file
 *     -> /billing/:customerId         their invoiceable days
 *         -> .../invoice/:date        the invoice
 *
 * Read-only. Every number is aggregated from orders; there are no
 * billing tables. See ARCHITECTURE.md.
 */
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import BillingRange, { useBillingRange } from '../components/BillingRange';
import { useBillingCustomers, useBillingSummary } from '../hooks/useBilling';
import { formatINR, formatPhone } from '../lib/format';

function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function SummaryCard({ label, value, sub, accent }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-3">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${accent ?? 'text-slate-900'}`}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Billing() {
  const [range, setRange] = useBillingRange();

  const summaryQuery = useBillingSummary(range);
  const customersQuery = useBillingCustomers(range);

  const summary = summaryQuery.data;
  const customers = customersQuery.data?.items ?? [];
  const isLoading = summaryQuery.isLoading || customersQuery.isLoading;
  const isError = summaryQuery.isError || customersQuery.isError;

  return (
    <>
      <div className="mb-3">
        <p className="text-sm font-medium text-slate-900">Billing</p>
        <p className="text-xs text-slate-500">
          Invoices are per customer, per day. Pick a customer to see their days.
        </p>
      </div>

      <BillingRange range={range} onChange={setRange} />

      {/* === Summary cards === */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mb-2.5">
        <SummaryCard
          label="Revenue"
          value={summary ? formatINR(summary.revenue) : '—'}
          sub={summary ? `${summary.order_count} orders` : null}
          accent="text-brand-700"
        />
        <SummaryCard
          label="Customers"
          value={summary ? summary.customer_count : '—'}
          sub="ordered in range"
        />
        <SummaryCard
          label="Orders"
          value={summary ? summary.order_count : '—'}
          sub="excluding cancelled"
        />
        <SummaryCard
          label="Cancelled"
          value={summary ? summary.cancelled_count : '—'}
          sub="not counted in revenue"
          accent={summary?.cancelled_count ? 'text-amber-600' : 'text-slate-900'}
        />
      </div>

      {/* === Customer list === */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
              <th className="px-3 py-2 font-medium">Customer</th>
              <th className="px-3 py-2 font-medium">Phone</th>
              <th className="px-3 py-2 font-medium text-right">Invoices</th>
              <th className="px-3 py-2 font-medium text-right">Orders</th>
              <th className="px-3 py-2 font-medium text-right">Total</th>
              <th className="px-3 py-2 font-medium w-8"></th>
            </tr>
          </thead>
          <tbody className="text-slate-900">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}

            {isError && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-red-700">
                  Could not load billing data.
                </td>
              </tr>
            )}

            {!isLoading && !isError && customers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  No orders in this range.
                </td>
              </tr>
            )}

            {customers.map((c) => (
              <tr
                key={c.customer_id}
                className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50"
              >
                <td className="px-3 py-2.5">
                  <Link
                    to={`/billing/${c.customer_id}?start=${range.start}&end=${range.end}`}
                    className="flex items-center gap-2"
                  >
                    <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-[10px] font-medium flex items-center justify-center">
                      {getInitials(c.customer_name)}
                    </div>
                    <span className="font-medium">{c.customer_name}</span>
                  </Link>
                </td>
                <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">
                  {formatPhone(c.primary_phone)}
                </td>
                <td className="px-3 py-2.5 text-right text-slate-700">{c.invoice_count}</td>
                <td className="px-3 py-2.5 text-right text-slate-700">{c.order_count}</td>
                <td className="px-3 py-2.5 text-right font-medium">{formatINR(c.total)}</td>
                <td className="px-3 py-2.5 text-right">
                  <Link
                    to={`/billing/${c.customer_id}?start=${range.start}&end=${range.end}`}
                    className="text-slate-400 hover:text-brand-600 inline-flex"
                    aria-label={`View invoices for ${c.customer_name}`}
                  >
                    <ChevronRight size={14} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
