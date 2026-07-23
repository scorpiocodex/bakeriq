/* eslint-disable react/react-in-jsx-scope */
/**
 * Billing — level 3 of the drill-down. The invoice itself.
 *
 * Covers one customer for one day, however many orders that day held.
 *
 * Printing goes through the browser rather than a server-side PDF
 * generator: no new dependency, and the owner can print to paper or to
 * PDF from the same dialog. The `print:` Tailwind variants plus the
 * @media block in index.css strip the app chrome.
 */
import { ArrowLeft, Printer } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { useBillingRange } from '../components/BillingRange';
import { useInvoice } from '../hooks/useBilling';
import { formatINR, formatPhone } from '../lib/format';

function formatLongDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Join the address parts that are present — all of them are optional. */
function addressLines(entity) {
  return [
    entity.address_line_1,
    entity.address_line_2,
    [entity.city, entity.state].filter(Boolean).join(', '),
    entity.pincode,
  ].filter(Boolean);
}

export default function BillingInvoice() {
  const { customerId, invoiceDate } = useParams();
  const [range] = useBillingRange();

  const { data: invoice, isLoading, isError, error } = useInvoice(customerId, invoiceDate);

  const backHref = `/billing/${customerId}?start=${range.start}&end=${range.end}`;
  const notFound = error?.response?.status === 404;

  if (isLoading) {
    return <p className="text-xs text-slate-500">Loading invoice…</p>;
  }

  if (isError) {
    return (
      <>
        <Link
          to={backHref}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-brand-600 mb-3"
        >
          <ArrowLeft size={12} />
          Back
        </Link>
        <div className="bg-white border border-slate-200 rounded-lg p-8 text-center">
          <p className="text-sm text-slate-700">
            {notFound ? 'No invoice for that date.' : 'Could not load the invoice.'}
          </p>
          {notFound && (
            <p className="text-xs text-slate-500 mt-1">
              This customer has no orders on {invoiceDate}.
            </p>
          )}
        </div>
      </>
    );
  }

  const { business, customer, orders } = invoice;

  return (
    <>
      {/* Toolbar — hidden when printing */}
      <div className="flex items-center justify-between mb-3 print:hidden">
        <Link
          to={backHref}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-brand-600"
        >
          <ArrowLeft size={12} />
          Back to invoices
        </Link>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
        >
          <Printer size={14} />
          Print / Save as PDF
        </button>
      </div>

      {/* The invoice sheet */}
      <div
        id="invoice-sheet"
        className="bg-white border border-slate-200 rounded-lg p-6 print:border-0 print:rounded-none print:p-0"
      >
        {/* Header: business (left) / invoice meta (right) */}
        <div className="flex justify-between items-start gap-6 pb-4 border-b border-slate-200">
          <div>
            <p className="text-lg font-semibold text-brand-700">{business.name}</p>
            {addressLines(business).map((line) => (
              <p key={line} className="text-xs text-slate-600 leading-snug">
                {line}
              </p>
            ))}
            {business.phone && (
              <p className="text-xs text-slate-600 leading-snug">{formatPhone(business.phone)}</p>
            )}
            {business.email && (
              <p className="text-xs text-slate-600 leading-snug">{business.email}</p>
            )}
          </div>

          <div className="text-right shrink-0">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
              Invoice
            </p>
            <p className="font-mono text-sm text-slate-900 mt-0.5">{invoice.invoice_number}</p>
            <p className="text-xs text-slate-600 mt-1">{formatLongDate(invoice.invoice_date)}</p>
          </div>
        </div>

        {/* Bill to */}
        <div className="py-4 border-b border-slate-200">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 font-medium mb-1">
            Bill to
          </p>
          <p className="text-sm font-medium text-slate-900">{customer.name}</p>
          <p className="text-xs text-slate-600">{formatPhone(customer.primary_phone)}</p>
          {addressLines(customer).map((line) => (
            <p key={line} className="text-xs text-slate-600 leading-snug">
              {line}
            </p>
          ))}
        </div>

        {/* One block per order — a day can hold several */}
        {orders.map((order, idx) => (
          <div
            key={order.id}
            className={`py-4 ${idx > 0 ? 'border-t border-slate-100' : ''} ${
              order.is_cancelled ? 'opacity-60' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-slate-700">Order #{order.short_id}</p>
              {order.is_cancelled && (
                <span className="text-[10px] px-2 py-0.5 bg-red-100 text-red-700 rounded font-medium">
                  Cancelled — not charged
                </span>
              )}
            </div>

            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 text-left border-b border-slate-100">
                  <th className="py-1.5 font-medium">Item</th>
                  <th className="py-1.5 font-medium text-right">Rate</th>
                  <th className="py-1.5 font-medium text-right">Qty</th>
                  <th className="py-1.5 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {order.items.map((line, i) => (
                  <tr key={i} className="border-b border-slate-50 last:border-b-0">
                    <td className="py-1.5 text-slate-900">{line.product_name}</td>
                    <td className="py-1.5 text-right text-slate-600">
                      {formatINR(line.unit_price)} / {line.unit_label}
                    </td>
                    <td className="py-1.5 text-right text-slate-600">{line.quantity}</td>
                    <td className="py-1.5 text-right text-slate-900">{formatINR(line.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {order.notes && (
              <p className="text-[11px] text-slate-500 mt-1.5 italic">Note: {order.notes}</p>
            )}

            <div className="flex justify-end mt-1.5">
              <p className="text-xs text-slate-600">
                Order total{' '}
                <span
                  className={`font-medium ${
                    order.is_cancelled ? 'line-through text-slate-400' : 'text-slate-900'
                  }`}
                >
                  {formatINR(order.total_amount)}
                </span>
              </p>
            </div>
          </div>
        ))}

        {/* Total */}
        <div className="pt-4 border-t-2 border-slate-300">
          <div className="flex justify-end">
            <div className="w-56">
              <div className="flex justify-between text-xs text-slate-600">
                <span>
                  {invoice.order_count} order{invoice.order_count === 1 ? '' : 's'}
                </span>
                {invoice.cancelled_count > 0 && (
                  <span className="text-slate-400">{invoice.cancelled_count} cancelled</span>
                )}
              </div>
              <div className="flex justify-between items-baseline mt-1.5">
                <span className="text-sm font-medium text-slate-700">Total</span>
                <span className="text-xl font-semibold text-brand-700">
                  {formatINR(invoice.total)}
                </span>
              </div>
            </div>
          </div>
        </div>

        <p className="text-[10px] text-slate-400 text-center mt-6">
          This is a computer-generated invoice and does not require a signature.
        </p>
      </div>
    </>
  );
}
