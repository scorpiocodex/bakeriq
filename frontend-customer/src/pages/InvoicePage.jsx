import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchInvoice } from '../lib/api';
import { formatRupees } from '../lib/format';

/**
 * Customer-facing invoice, opened from the WhatsApp "View invoice"
 * button. Shows their latest invoice — every order on the day of their
 * most recent one.
 *
 * No download button: on a phone, the browser's own share sheet already
 * offers Print / Save as PDF, and it does a better job than anything we
 * could bolt on. On desktop, Ctrl+P.
 */

function formatLongDate(iso) {
  // Split the ISO string rather than parsing it — new Date('2026-07-13')
  // is treated as UTC and renders as the 12th in some zones.
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Join whichever address parts are present — all of them are optional. */
function addressLines(entity) {
  return [
    entity.address_line_1,
    entity.address_line_2,
    [entity.city, entity.state].filter(Boolean).join(', '),
    entity.pincode,
  ].filter(Boolean);
}

export default function InvoicePage() {
  const { token } = useParams();

  const {
    data: invoice,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['invoice', token],
    queryFn: () => fetchInvoice(token),
    enabled: Boolean(token),
    // A 404 is a real answer — expired link, or no orders yet. Retrying
    // just delays showing it.
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <p className="text-gray-600">Loading your invoice…</p>
      </div>
    );
  }

  if (isError) {
    const detail = error?.response?.data?.detail;
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-red-200 p-4">
          <p className="font-semibold text-red-700">Invoice not available</p>
          <p className="text-sm text-gray-700 mt-2">
            {detail ||
              'This link has expired or is no longer valid. Message BakeriQ on WhatsApp for a fresh one.'}
          </p>
        </div>
      </div>
    );
  }

  const { business, customer, orders } = invoice;

  return (
    <div className="app-container pb-8">
      <header className="mb-4 print:hidden">
        <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        <p className="mt-1 text-sm text-gray-600">Your invoice</p>
      </header>

      <div className="bg-white rounded-lg shadow-sm border border-brand-100 p-4 print:border-0 print:shadow-none print:p-0">
        {/* Business */}
        <div className="pb-3 border-b border-gray-200">
          <p className="text-lg font-bold text-brand-700">{business.name}</p>
          {addressLines(business).map((line) => (
            <p key={line} className="text-xs text-gray-600 leading-snug">
              {line}
            </p>
          ))}
          {business.phone && <p className="text-xs text-gray-600 leading-snug">{business.phone}</p>}
        </div>

        {/* Invoice meta */}
        <div className="py-3 border-b border-gray-200">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Invoice</p>
          <p className="font-mono text-sm text-gray-900">{invoice.invoice_number}</p>
          <p className="text-xs text-gray-600 mt-0.5">{formatLongDate(invoice.invoice_date)}</p>
        </div>

        {/* Bill to */}
        <div className="py-3 border-b border-gray-200">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 font-medium mb-1">
            Bill to
          </p>
          <p className="text-sm font-medium text-gray-900">{customer.name}</p>
          <p className="text-xs text-gray-600">{customer.primary_phone}</p>
          {addressLines(customer).map((line) => (
            <p key={line} className="text-xs text-gray-600 leading-snug">
              {line}
            </p>
          ))}
        </div>

        {/* Orders — a day can hold more than one */}
        {orders.map((order, idx) => (
          <div
            key={order.id}
            className={`py-3 ${idx > 0 ? 'border-t border-gray-100' : ''} ${
              order.is_cancelled ? 'opacity-60' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-medium text-gray-700">Order #{order.short_id}</p>
              {order.is_cancelled && (
                <span className="text-[10px] px-2 py-0.5 bg-red-100 text-red-700 rounded font-medium">
                  Cancelled
                </span>
              )}
            </div>

            {order.items.map((line, i) => (
              <div key={i} className="flex justify-between text-sm py-1">
                <div className="min-w-0">
                  <p className="text-gray-900">{line.product_name}</p>
                  <p className="text-xs text-gray-500">
                    {line.quantity} × {formatRupees(line.unit_price)} / {line.unit_label}
                  </p>
                </div>
                <p className="text-gray-900 shrink-0 ml-3">{formatRupees(line.subtotal)}</p>
              </div>
            ))}

            {order.notes && (
              <p className="text-xs text-gray-500 mt-1 italic">Note: {order.notes}</p>
            )}
          </div>
        ))}

        {/* Total */}
        <div className="pt-3 border-t-2 border-gray-300">
          <div className="flex justify-between items-baseline">
            <span className="text-sm font-medium text-gray-700">
              Total
              {invoice.cancelled_count > 0 && (
                <span className="text-xs text-gray-400 font-normal">
                  {' '}
                  ({invoice.cancelled_count} cancelled, not charged)
                </span>
              )}
            </span>
            <span className="text-xl font-bold text-brand-700">{formatRupees(invoice.total)}</span>
          </div>
        </div>

        <p className="text-[10px] text-gray-400 text-center mt-4">
          Computer-generated invoice — no signature required.
        </p>
      </div>

      <p className="text-xs text-gray-500 text-center mt-4 print:hidden">
        To save a copy, use your browser&apos;s Share or Print option.
      </p>
    </div>
  );
}
