/**
 * Modal for creating or editing an order.
 *
 * Create mode: pick a customer, optionally "Load default order" to pre-fill
 * items from their template, edit rows, save.
 * Edit mode: pre-filled from an existing order; can change date/notes/items.
 * (Status is changed from the detail panel, not here.)
 *
 * Multi-row item editor: product dropdown + quantity per row, add/remove.
 * Prices shown are current product prices; the server snapshots on save.
 */
import { useEffect, useState } from 'react';

import { useCustomersList } from '../hooks/useCustomers';
import { useCreateOrder, useOrderPrefill, useUpdateOrder } from '../hooks/useOrders';
import { useProductsList } from '../hooks/useProducts';

function blankRow() {
    return { product_id: '', quantity: 1 };
}

function todayStr() {
    return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

export default function OrderFormModal({ open, mode, order, onClose }) {
    const [customerId, setCustomerId] = useState('');
    const [orderDate, setOrderDate] = useState(todayStr());
    const [notes, setNotes] = useState('');
    const [rows, setRows] = useState([blankRow()]);
    const [error, setError] = useState('');
    const [prefillNote, setPrefillNote] = useState('');

    const customersQuery = useCustomersList({ status: 'active', limit: 200 });
    const productsQuery = useProductsList({ status: 'active', limit: 200 });
    const customers = customersQuery.data?.items ?? [];
    const products = productsQuery.data?.items ?? [];

    const createMut = useCreateOrder();
    const updateMut = useUpdateOrder();
    const prefillMut = useOrderPrefill();

    const isSubmitting = createMut.isPending || updateMut.isPending;

    useEffect(() => {
        if (!open) return;
        if (mode === 'edit' && order) {
            setCustomerId(order.customer_id);
            setOrderDate(order.order_date);
            setNotes(order.notes ?? '');
            setRows(
                order.items.length > 0
                    ? order.items.map((it) => ({ product_id: it.product_id, quantity: it.quantity }))
                    : [blankRow()],
            );
        } else {
            setCustomerId('');
            setOrderDate(todayStr());
            setNotes('');
            setRows([blankRow()]);
        }
        setError('');
        setPrefillNote('');
    }, [open, mode, order]);

    if (!open) return null;

    function updateRow(index, field, value) {
        setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
    }
    function addRow() {
        setRows((prev) => [...prev, blankRow()]);
    }
    function removeRow(index) {
        setRows((prev) => prev.filter((_, i) => i !== index));
    }

    async function handleLoadDefault() {
        setError('');
        setPrefillNote('');
        if (!customerId) {
            setError('Pick a customer first, then load their default order.');
            return;
        }
        try {
            const result = await prefillMut.mutateAsync(customerId);
            if (result.items.length === 0) {
                setPrefillNote('This customer has no default order template.');
                return;
            }
            // Replace rows with the template's suggestions
            setRows(result.items.map((it) => ({ product_id: it.product_id, quantity: it.quantity })));
            if (result.skipped_count > 0) {
                setPrefillNote(
                    `Loaded ${result.items.length} item(s). ${result.skipped_count} item(s) skipped — no longer available.`,
                );
            } else {
                setPrefillNote(`Loaded ${result.items.length} item(s) from default order.`);
            }
        } catch {
            setError('Could not load the default order.');
        }
    }

    async function handleSubmit() {
        setError('');

        if (!customerId) {
            setError('Please select a customer.');
            return;
        }

        const validRows = rows.filter((r) => r.product_id);
        if (validRows.length === 0) {
            setError('An order needs at least one item.');
            return;
        }
        for (const r of validRows) {
            const q = Number(r.quantity);
            if (!Number.isInteger(q) || q <= 0) {
                setError('All quantities must be whole numbers greater than 0.');
                return;
            }
        }
        const ids = validRows.map((r) => r.product_id);
        if (new Set(ids).size !== ids.length) {
            setError('Each product can only appear once. Combine duplicate rows.');
            return;
        }

        const items = validRows.map((r) => ({ product_id: r.product_id, quantity: Number(r.quantity) }));

        try {
            if (mode === 'edit') {
                // Status excluded — handled in the detail panel
                await updateMut.mutateAsync({
                    id: order.id,
                    payload: { order_date: orderDate, notes: notes.trim() || null, items },
                });
            } else {
                await createMut.mutateAsync({
                    customer_id: customerId,
                    order_date: orderDate,
                    notes: notes.trim() || null,
                    items,
                });
            }
            onClose();
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(typeof detail === 'string' ? detail : 'Could not save the order. Please check and try again.');
        }
    }

    // Running total preview from current product prices (display only; server
    // snapshots authoritatively on save)
    function rowSubtotal(row) {
        const p = products.find((x) => x.id === row.product_id);
        if (!p) return 0;
        return Number(p.unit_price) * Number(row.quantity || 0);
    }
    const previewTotal = rows.reduce((sum, r) => sum + rowSubtotal(r), 0);

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="order-modal-title"
        >
            <div
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto"
            >
                <div className="flex items-center justify-between mb-4">
                    <h2 id="order-modal-title" className="text-base font-medium text-slate-900">
                        {mode === 'edit' ? 'Edit order' : 'New order'}
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

                {error && (
                    <div role="alert" className="bg-red-50 border border-red-200 text-red-800 text-sm px-3 py-2 rounded-lg mb-4">
                        {error}
                    </div>
                )}

                {/* Customer + date row */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                    <div>
                        <label htmlFor="of-customer" className="block text-sm text-slate-700 mb-1">
                            Customer <span className="text-red-600">*</span>
                        </label>
                        <select
                            id="of-customer"
                            value={customerId}
                            onChange={(e) => setCustomerId(e.target.value)}
                            disabled={mode === 'edit'}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500"
                        >
                            <option value="">Select a customer…</option>
                            {customers.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.name} ({c.primary_phone})
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="of-date" className="block text-sm text-slate-700 mb-1">
                            Order date
                        </label>
                        <input
                            id="of-date"
                            type="date"
                            value={orderDate}
                            onChange={(e) => setOrderDate(e.target.value)}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>
                </div>

                {/* Load default order (create mode only) */}
                {mode !== 'edit' && (
                    <div className="mb-4">
                        <button
                            type="button"
                            onClick={handleLoadDefault}
                            disabled={prefillMut.isPending || !customerId}
                            className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 rounded-md font-medium"
                        >
                            {prefillMut.isPending ? 'Loading…' : '↓ Load default order'}
                        </button>
                        {prefillNote && (
                            <span className="ml-2 text-xs text-slate-500">{prefillNote}</span>
                        )}
                    </div>
                )}

                {/* Item rows */}
                <div className="space-y-2 mb-4">
                    <div className="flex items-center gap-2 text-xs text-slate-500 font-medium px-1">
                        <span className="flex-1">Product</span>
                        <span className="w-20">Qty</span>
                        <span className="w-24 text-right">Subtotal</span>
                        <span className="w-6"></span>
                    </div>

                    {rows.map((row, index) => (
                        <div key={index} className="flex items-center gap-2">
                            <select
                                value={row.product_id}
                                onChange={(e) => updateRow(index, 'product_id', e.target.value)}
                                className="flex-1 text-sm px-3 py-2 border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            >
                                <option value="">Select a product…</option>
                                {products.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.name} — ₹{Number(p.unit_price).toFixed(2)}/{p.unit_label}
                                    </option>
                                ))}
                            </select>
                            <input
                                type="number"
                                min="1"
                                value={row.quantity}
                                onChange={(e) => updateRow(index, 'quantity', e.target.value)}
                                className="w-20 text-sm px-3 py-2 border border-slate-300 rounded-lg font-mono focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />
                            <span className="w-24 text-right text-sm font-mono text-slate-700">
                                ₹{rowSubtotal(row).toFixed(2)}
                            </span>
                            <button
                                type="button"
                                onClick={() => removeRow(index)}
                                className="w-6 text-slate-400 hover:text-red-600 text-lg leading-none"
                                aria-label="Remove row"
                            >
                                ×
                            </button>
                        </div>
                    ))}

                    <button
                        type="button"
                        onClick={addRow}
                        className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                    >
                        + Add another product
                    </button>
                </div>

                {/* Total preview */}
                <div className="flex justify-end mb-4 pt-2 border-t border-slate-200">
                    <span className="text-sm text-slate-700">
                        Total: <span className="font-mono font-medium">₹{previewTotal.toFixed(2)}</span>
                    </span>
                </div>

                {/* Notes */}
                <div className="mb-4">
                    <label htmlFor="of-notes" className="block text-sm text-slate-700 mb-1">
                        Notes <span className="text-slate-400">(optional)</span>
                    </label>
                    <input
                        id="of-notes"
                        type="text"
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="e.g. ring the bell, no onions"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                    />
                </div>

                {/* Footer */}
                <div className="flex gap-2 pt-4 border-t border-slate-200">
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="flex-1 py-2 text-sm bg-white text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={handleSubmit}
                        disabled={isSubmitting}
                        className="flex-1 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white rounded-lg font-medium"
                    >
                        {isSubmitting ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Create order'}
                    </button>
                </div>
            </div>
        </div>
    );
}