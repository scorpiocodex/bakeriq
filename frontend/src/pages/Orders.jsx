/**
 * Orders page — list of all orders with filters, plus the detail panel and
 * create/edit modal.
 *
 * Layout:
 *   - Header (title + count + "New order")
 *   - Filter card (status chips, date filter, customer filter)
 *   - Table of compact rows; click a row to open the detail panel
 *
 * Overlays: OrderDetailPanel (right drawer), OrderFormModal (create/edit),
 * ConfirmDialog (delete).
 */
import { useState } from 'react';

import ConfirmDialog from '../components/ConfirmDialog';
import OrderDetailPanel from '../components/OrderDetailPanel';
import OrderFormModal from '../components/OrderFormModal';
import { useCustomersList } from '../hooks/useCustomers';
import { useDeleteOrder, useOrdersList } from '../hooks/useOrders';

const STATUS_FILTERS = [
    { key: null, label: 'All' },
    { key: 'received', label: 'Received' },
    { key: 'preparing', label: 'Preparing' },
    { key: 'ready', label: 'Ready' },
    { key: 'delivering', label: 'Delivering' },
    { key: 'cancelled', label: 'Cancelled' },
];

const STATUS_STYLES = {
    received: 'bg-slate-100 text-slate-700',
    preparing: 'bg-amber-100 text-amber-800',
    ready: 'bg-blue-100 text-blue-800',
    delivering: 'bg-teal-100 text-teal-800',
    cancelled: 'bg-red-100 text-red-700',
};

const STATUS_LABELS = {
    received: 'Received',
    preparing: 'Preparing',
    ready: 'Ready',
    delivering: 'Delivering',
    cancelled: 'Cancelled',
};

export default function Orders() {
    const [activeStatus, setActiveStatus] = useState(null);
    const [orderDate, setOrderDate] = useState('');
    const [customerId, setCustomerId] = useState('');

    // Detail panel
    const [selectedOrderId, setSelectedOrderId] = useState(null);
    // Form modal
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState('create');
    const [editingOrder, setEditingOrder] = useState(null);
    // Delete
    const [deleteTarget, setDeleteTarget] = useState(null);

    const filters = {};
    if (activeStatus) filters.status = activeStatus;
    if (orderDate) filters.orderDate = orderDate;
    if (customerId) filters.customerId = customerId;

    const { data, isLoading, isError, error } = useOrdersList(filters);
    const customersQuery = useCustomersList({ status: 'active', limit: 200 });
    const deleteMut = useDeleteOrder();

    const orders = data?.items ?? [];
    const total = data?.total ?? 0;
    const customers = customersQuery.data?.items ?? [];

    function openCreate() {
        setModalMode('create');
        setEditingOrder(null);
        setModalOpen(true);
    }

    function openEdit(order) {
        setModalMode('edit');
        setEditingOrder(order);
        setModalOpen(true);
        setSelectedOrderId(null); // close the panel when entering edit
    }

    async function handleDeleteConfirm() {
        if (!deleteTarget) return;
        try {
            await deleteMut.mutateAsync(deleteTarget.id);
            setSelectedOrderId(null); // close panel if the deleted order was open
        } catch {
            // surfaced via deleteMut if needed
        } finally {
            setDeleteTarget(null);
        }
    }

    return (
        <>
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div>
                    <p className="text-sm font-medium text-slate-900">Orders</p>
                    <p className="text-xs text-slate-500">
                        {isLoading ? 'Loading…' : `${total} order${total === 1 ? '' : 's'}`}
                    </p>
                </div>
                <button
                    onClick={openCreate}
                    className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
                >
                    + New order
                </button>
            </div>

            {/* Filter card */}
            <div className="bg-white border border-slate-200 rounded-lg p-2.5 mb-2.5 space-y-2">
                <div className="flex flex-wrap items-center gap-1.5">
                    {STATUS_FILTERS.map((f) => (
                        <button
                            key={f.key ?? 'all'}
                            onClick={() => setActiveStatus(f.key)}
                            className={`text-xs px-3 py-1 rounded-full border ${activeStatus === f.key
                                    ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
                                }`}
                        >
                            {f.label}
                        </button>
                    ))}
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100">
                    <label className="text-xs text-slate-500">Date:</label>
                    <input
                        type="date"
                        value={orderDate}
                        onChange={(e) => setOrderDate(e.target.value)}
                        className="text-xs px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                    />
                    {orderDate && (
                        <button
                            onClick={() => setOrderDate('')}
                            className="text-xs text-slate-500 hover:text-slate-700"
                        >
                            clear
                        </button>
                    )}

                    <label className="text-xs text-slate-500 ml-3">Customer:</label>
                    <select
                        value={customerId}
                        onChange={(e) => setCustomerId(e.target.value)}
                        className="text-xs px-2 py-1 border border-slate-300 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                    >
                        <option value="">All customers</option>
                        {customers.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
                            <th className="px-3 py-2 font-medium">Customer</th>
                            <th className="px-3 py-2 font-medium">Date</th>
                            <th className="px-3 py-2 font-medium">Items</th>
                            <th className="px-3 py-2 font-medium">Total</th>
                            <th className="px-3 py-2 font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody className="text-slate-900">
                        {isLoading && (
                            <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">Loading orders…</td></tr>
                        )}
                        {isError && (
                            <tr><td colSpan={5} className="px-3 py-8 text-center text-red-700">
                                Could not load orders: {error?.message ?? 'unknown error'}
                            </td></tr>
                        )}
                        {!isLoading && !isError && orders.length === 0 && (
                            <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                                {activeStatus || orderDate || customerId
                                    ? 'No orders match your filters.'
                                    : 'No orders yet. Click "+ New order" to create the first one.'}
                            </td></tr>
                        )}
                        {orders.map((o) => (
                            <tr
                                key={o.id}
                                onClick={() => setSelectedOrderId(o.id)}
                                className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50 cursor-pointer"
                            >
                                <td className="px-3 py-2.5">
                                    <div className="font-medium">{o.customer.name}</div>
                                    <div className="text-[11px] text-slate-500">{o.customer.primary_phone}</div>
                                </td>
                                <td className="px-3 py-2.5 text-slate-700">{o.order_date}</td>
                                <td className="px-3 py-2.5 text-slate-700">{o.item_count}</td>
                                <td className="px-3 py-2.5 font-mono text-slate-700">₹{Number(o.total_amount).toFixed(2)}</td>
                                <td className="px-3 py-2.5">
                                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[o.status]}`}>
                                        {STATUS_LABELS[o.status]}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Detail panel */}
            <OrderDetailPanel
                orderId={selectedOrderId}
                open={selectedOrderId !== null}
                onClose={() => setSelectedOrderId(null)}
                onEdit={openEdit}
                onDelete={(order) => setDeleteTarget(order)}
            />

            {/* Create/edit modal */}
            <OrderFormModal
                open={modalOpen}
                mode={modalMode}
                order={editingOrder}
                onClose={() => setModalOpen(false)}
            />

            {/* Delete confirmation */}
            <ConfirmDialog
                open={deleteTarget !== null}
                title="Delete order?"
                message={
                    deleteTarget
                        ? `This order for ${deleteTarget.customer.name} will be permanently deleted. For real orders you usually want to cancel instead (which keeps the record). This cannot be undone.`
                        : ''
                }
                confirmLabel="Delete permanently"
                destructive
                isProcessing={deleteMut.isPending}
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteTarget(null)}
            />
        </>
    );
}