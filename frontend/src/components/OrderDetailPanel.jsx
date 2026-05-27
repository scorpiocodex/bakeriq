/**
 * Right-side drawer showing one order's full detail: customer, line items,
 * total, notes, and status-change controls.
 *
 * Slides in from the right when an order is selected on the Orders page.
 * Status changes happen here (not in the edit modal) — quick action buttons
 * for the next states plus a cancel option. Edit and delete are also exposed.
 */
import { useChangeOrderStatus, useOrder } from '../hooks/useOrders';

const STATUS_LABELS = {
    received: 'Received',
    preparing: 'Preparing',
    ready: 'Ready',
    delivering: 'Delivering',
    cancelled: 'Cancelled',
};

const STATUS_STYLES = {
    received: 'bg-slate-100 text-slate-700',
    preparing: 'bg-amber-100 text-amber-800',
    ready: 'bg-blue-100 text-blue-800',
    delivering: 'bg-teal-100 text-teal-800',
    cancelled: 'bg-red-100 text-red-700',
};

// The forward chain — used to offer "advance to next" buttons.
const FORWARD = ['received', 'preparing', 'ready', 'delivering'];

function nextStatuses(current) {
    // Offer the next forward step (if any). Cancel is offered separately.
    const idx = FORWARD.indexOf(current);
    if (idx === -1 || idx === FORWARD.length - 1) return [];
    return [FORWARD[idx + 1]];
}

export default function OrderDetailPanel({ orderId, open, onClose, onEdit, onDelete }) {
    const { data: order, isLoading, isError, error } = useOrder(orderId, { enabled: open });
    const statusMut = useChangeOrderStatus();

    if (!open) return null;

    async function handleStatusChange(newStatus) {
        try {
            await statusMut.mutateAsync({ id: orderId, status: newStatus });
        } catch {
            // Error surfaces via statusMut.isError if needed; panel stays open
        }
    }

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 z-40 bg-slate-900/20"
                onClick={onClose}
                aria-hidden="true"
            />

            {/* Drawer */}
            <div
                className="fixed right-0 top-0 z-50 h-full w-full max-w-md bg-white shadow-xl border-l border-slate-200 overflow-y-auto"
                role="dialog"
                aria-modal="true"
                aria-labelledby="order-detail-title"
            >
                <div className="p-5">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-4">
                        <h2 id="order-detail-title" className="text-base font-medium text-slate-900">
                            Order detail
                        </h2>
                        <button
                            type="button"
                            onClick={onClose}
                            className="text-slate-400 hover:text-slate-600 text-xl leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>

                    {isLoading && (
                        <p className="text-sm text-slate-500 py-8 text-center">Loading order…</p>
                    )}

                    {isError && (
                        <p className="text-sm text-red-700 py-8 text-center">
                            Could not load order: {error?.message ?? 'unknown error'}
                        </p>
                    )}

                    {!isLoading && !isError && order && (
                        <>
                            {/* Customer */}
                            <div className="mb-4 pb-4 border-b border-slate-100">
                                <p className="text-sm font-medium text-slate-900">{order.customer.name}</p>
                                <p className="text-xs text-slate-500">{order.customer.primary_phone}</p>
                            </div>

                            {/* Status + date */}
                            <div className="flex items-center justify-between mb-4">
                                <span
                                    className={`text-xs px-2.5 py-1 rounded-full font-medium ${STATUS_STYLES[order.status]}`}
                                >
                                    {STATUS_LABELS[order.status]}
                                </span>
                                <span className="text-xs text-slate-500">{order.order_date}</span>
                            </div>

                            {/* Status controls */}
                            {order.status !== 'cancelled' && (
                                <div className="flex flex-wrap gap-2 mb-4">
                                    {nextStatuses(order.status).map((s) => (
                                        <button
                                            key={s}
                                            onClick={() => handleStatusChange(s)}
                                            disabled={statusMut.isPending}
                                            className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-md font-medium"
                                        >
                                            Mark as {STATUS_LABELS[s]}
                                        </button>
                                    ))}
                                    <button
                                        onClick={() => handleStatusChange('cancelled')}
                                        disabled={statusMut.isPending}
                                        className="text-xs px-3 py-1.5 bg-white border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50 rounded-md font-medium"
                                    >
                                        Cancel order
                                    </button>
                                </div>
                            )}

                            {/* Line items */}
                            <div className="mb-4">
                                <p className="text-xs uppercase tracking-wide text-slate-500 font-medium mb-2">
                                    Items
                                </p>
                                <div className="space-y-1.5">
                                    {order.items.map((item) => (
                                        <div key={item.id} className="flex items-center justify-between text-sm">
                                            <span className="text-slate-700">
                                                {item.product_name}
                                                <span className="text-slate-400 text-xs ml-1">
                                                    × {item.quantity}
                                                </span>
                                            </span>
                                            <span className="font-mono text-slate-700">
                                                ₹{Number(item.subtotal).toFixed(2)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-200">
                                    <span className="text-sm font-medium text-slate-900">Total</span>
                                    <span className="font-mono font-medium text-slate-900">
                                        ₹{Number(order.total_amount).toFixed(2)}
                                    </span>
                                </div>
                            </div>

                            {/* Notes */}
                            {order.notes && (
                                <div className="mb-4 pb-4 border-b border-slate-100">
                                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium mb-1">
                                        Notes
                                    </p>
                                    <p className="text-sm text-slate-700">{order.notes}</p>
                                </div>
                            )}

                            {/* Edit / delete */}
                            <div className="flex gap-2 pt-2">
                                <button
                                    onClick={() => onEdit(order)}
                                    className="flex-1 py-2 text-sm bg-white text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50"
                                >
                                    Edit order
                                </button>
                                <button
                                    onClick={() => onDelete(order)}
                                    className="py-2 px-3 text-sm text-red-600 hover:text-red-700"
                                >
                                    Delete
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </>
    );
}