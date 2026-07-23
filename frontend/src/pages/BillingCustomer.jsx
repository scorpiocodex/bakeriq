/* eslint-disable react/react-in-jsx-scope */
/**
 * Billing — level 2 of the drill-down.
 *
 * One customer's invoiceable days within the range. Each row is one
 * invoice, however many orders that day contained.
 */
import { ArrowLeft, ChevronRight, FileText } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import BillingRange, { useBillingRange } from '../components/BillingRange';
import { useCustomerInvoiceDates } from '../hooks/useBilling';
import { formatINR, formatPhone } from '../lib/format';

function formatLongDate(iso) {
  // Parsed as UTC then rendered in IST would shift the date across the
  // boundary, so split the ISO string rather than going through Date.
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export default function BillingCustomer() {
  const { customerId } = useParams();
  const [range, setRange] = useBillingRange();

  const { data, isLoading, isError, error } = useCustomerInvoiceDates(customerId, range);

  const customer = data?.customer;
  const days = data?.items ?? [];
  const rangeQuery = `?start=${range.start}&end=${range.end}`;

  const notFound = error?.response?.status === 404;

  return (
    <>
      <div className="mb-3">
        <Link
          to={`/billing${rangeQuery}`}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-brand-600 mb-1"
        >
          <ArrowLeft size={12} />
          Back to billing
        </Link>
        <p className="text-sm font-medium text-slate-900">
          {customer ? customer.name : 'Invoices'}
        </p>
        <p className="text-xs text-slate-500">
          {customer
            ? `${formatPhone(customer.primary_phone)} · ${days.length} invoice${
                days.length === 1 ? '' : 's'
              } in range`
            : 'Loading…'}
        </p>
      </div>

      <BillingRange range={range} onChange={setRange} />

      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
              <th className="px-3 py-2 font-medium">Date</th>
              <th className="px-3 py-2 font-medium">Invoice no.</th>
              <th className="px-3 py-2 font-medium text-right">Orders</th>
              <th className="px-3 py-2 font-medium text-right">Total</th>
              <th className="px-3 py-2 font-medium w-8"></th>
            </tr>
          </thead>
          <tbody className="text-slate-900">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}

            {isError && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-red-700">
                  {notFound ? 'Customer not found.' : 'Could not load invoices.'}
                </td>
              </tr>
            )}

            {!isLoading && !isError && days.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  No orders in this range.
                </td>
              </tr>
            )}

            {days.map((d) => {
              const href = `/billing/${customerId}/invoice/${d.order_date}${rangeQuery}`;
              return (
                <tr
                  key={d.order_date}
                  className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50"
                >
                  <td className="px-3 py-2.5">
                    <Link to={href} className="flex items-center gap-2 font-medium">
                      <FileText size={14} className="text-slate-400" />
                      {formatLongDate(d.order_date)}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">
                    {d.invoice_number}
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-700">{d.order_count}</td>
                  <td className="px-3 py-2.5 text-right font-medium">{formatINR(d.total)}</td>
                  <td className="px-3 py-2.5 text-right">
                    <Link
                      to={href}
                      className="text-slate-400 hover:text-brand-600 inline-flex"
                      aria-label={`Open invoice ${d.invoice_number}`}
                    >
                      <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
