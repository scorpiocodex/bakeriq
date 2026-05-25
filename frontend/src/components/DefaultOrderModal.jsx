/**
 * Modal for managing a customer's default order template.
 *
 * Opened from the Customers page via a "Default order" row action.
 * Self-contained: fetches the customer's template on open, lets the owner
 * add/remove item rows (product + quantity), edit notes, toggle active,
 * and save the whole thing via the customer-scoped PUT.
 *
 * The template is "replace-all" — whatever rows are in the editor when you
 * hit Save become the complete template. Removing a row and saving removes
 * that item.
 *
 * States handled:
 *   - Loading the existing template
 *   - No template yet (empty editor, ready to add)
 *   - Existing template (pre-filled rows)
 *   - Saving
 *   - Delete entire template
 */
import { useEffect, useState } from 'react';

import {
    useDefaultOrder,
    useDeleteDefaultOrder,
    useUpsertDefaultOrder,
} from '../hooks/useDefaultOrders';
import { useProductsList } from '../hooks/useProducts';
import ConfirmDialog from './ConfirmDialog';

// A blank item row — product not yet chosen, quantity defaults to 1.
function blankRow() {
    return { product_id: '', quantity: 1 };
}

export default function DefaultOrderModal({ open, customer, onClose }) {
    const customerId = customer?.id ?? null;

    // ---- Form state ----
    const [notes, setNotes] = useState('');
    const [isActive, setIsActive] = useState(true);
    const [rows, setRows] = useState([blankRow()]);
    const [error, setError] = useState('');
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

    // ---- Server state ----
    // Fetch the template only when the modal is open and we have a customer.
    const {
        data: template,
        isLoading,
        isError,
        error: fetchError,
    } = useDefaultOrder(customerId, { enabled: open });

    // Product list for the dropdowns — active products only.
    const productsQuery = useProductsList({ status: 'active', limit: 200 });
    const products = productsQuery.data?.items ?? [];

    const upsertMut = useUpsertDefaultOrder();
    const deleteMut = useDeleteDefaultOrder();

    // ---- Effect: populate form when template loads / modal opens ----
    useEffect(() => {
        if (!open) return;

        if (template) {
            // Existing template — pre-fill
            setNotes(template.notes ?? '');
            setIsActive(template.is_active ?? true);
            setRows(
                template.items.length > 0
                    ? template.items.map((item) => ({
                        product_id: item.product_id,
                        quantity: item.quantity,
                    }))
                    : [blankRow()],
            );
        } else {
            // No template (null) — empty editor
            setNotes('');
            setIsActive(true);
            setRows([blankRow()]);
        }
        setError('');
    }, [open, template]);

    if (!open) return null;

    // ---- Row handlers ----
    function updateRow(index, field, value) {
        setRows((prev) =>
            prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
        );
    }

    function addRow() {
        setRows((prev) => [...prev, blankRow()]);
    }

    function removeRow(index) {
        setRows((prev) => prev.filter((_, i) => i !== index));
    }

    // ---- Submit ----
    async function handleSave() {
        setError('');

        // Filter out rows with no product selected — they're incomplete and
        // shouldn't be sent. A template with zero valid rows is allowed (it
        // just means "empty template").
        const validRows = rows.filter((r) => r.product_id);

        // Validate quantities
        for (const row of validRows) {
            const qty = Number(row.quantity);
            if (!Number.isInteger(qty) || qty <= 0) {
                setError('All quantities must be whole numbers greater than 0.');
                return;
            }
        }

        // Guard against duplicate products in the same template — the bakery
        // owner probably meant to combine them. Backend would accept duplicates
        // but it's almost certainly a mistake.
        const productIds = validRows.map((r) => r.product_id);
        if (new Set(productIds).size !== productIds.length) {
            setError('Each product can only appear once. Combine duplicate rows.');
            return;
        }

        const payload = {
            notes: notes.trim() || null,
            is_active: isActive,
            items: validRows.map((r) => ({
                product_id: r.product_id,
                quantity: Number(r.quantity),
            })),
        };

        try {
            await upsertMut.mutateAsync({ customerId, payload });
            onClose();
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(
                typeof detail === 'string'
                    ? detail
                    : 'Could not save the default order. Please check and try again.',
            );
        }
    }

    async function handleDeleteConfirm() {
        try {
            await deleteMut.mutateAsync(customerId);
            setDeleteConfirmOpen(false);
            onClose();
        } catch (err) {
            // If there's no template to delete (404), just close — same end state
            setDeleteConfirmOpen(false);
            onClose();
        }
    }

    const isSubmitting = upsertMut.isPending || deleteMut.isPending;
    const hasExistingTemplate = Boolean(template);

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="default-order-modal-title"
        >
            <div
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto"
            >
                {/* Header */}
                <div className="flex items-center justify-between mb-1">
                    <h2 id="default-order-modal-title" className="text-base font-medium text-slate-900">
                        Default order
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
                <p className="text-xs text-slate-500 mb-4">
                    {customer?.name}'s usual order — used by the bot to draft daily messages
                </p>

                {/* Loading state */}
                {isLoading && (
                    <p className="text-sm text-slate-500 py-8 text-center">Loading template…</p>
                )}

                {/* Error state (real errors, not 404) */}
                {isError && (
                    <p className="text-sm text-red-700 py-8 text-center">
                        Could not load template: {fetchError?.message ?? 'unknown error'}
                    </p>
                )}

                {/* Editor — shown once not loading and no fetch error */}
                {!isLoading && !isError && (
                    <>
                        {/* Error banner */}
                        {error && (
                            <div role="alert" className="bg-red-50 border border-red-200 text-red-800 text-sm px-3 py-2 rounded-lg mb-4">
                                {error}
                            </div>
                        )}

                        {/* Item rows */}
                        <div className="space-y-2 mb-4">
                            <div className="flex items-center gap-2 text-xs text-slate-500 font-medium px-1">
                                <span className="flex-1">Product</span>
                                <span className="w-20">Quantity</span>
                                <span className="w-6"></span>
                            </div>

                            {rows.map((row, index) => (
                                <div key={index} className="flex items-center gap-2">
                                    {/* Product dropdown */}
                                    <select
                                        value={row.product_id}
                                        onChange={(e) => updateRow(index, 'product_id', e.target.value)}
                                        className="flex-1 text-sm px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 bg-white"
                                    >
                                        <option value="">Select a product…</option>
                                        {products.map((p) => (
                                            <option key={p.id} value={p.id}>
                                                {p.name} — ₹{Number(p.unit_price).toFixed(2)}/{p.unit_label}
                                            </option>
                                        ))}
                                    </select>

                                    {/* Quantity */}
                                    <input
                                        type="number"
                                        min="1"
                                        value={row.quantity}
                                        onChange={(e) => updateRow(index, 'quantity', e.target.value)}
                                        className="w-20 text-sm px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 font-mono"
                                    />

                                    {/* Remove row */}
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

                            {/* Add row */}
                            <button
                                type="button"
                                onClick={addRow}
                                className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                            >
                                + Add another product
                            </button>
                        </div>

                        {/* Notes */}
                        <div className="mb-4">
                            <label htmlFor="do-notes" className="block text-sm text-slate-700 mb-1">
                                Notes <span className="text-slate-400">(optional)</span>
                            </label>
                            <input
                                id="do-notes"
                                type="text"
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                placeholder="e.g. skip Sundays, deliver before 8 AM"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />
                        </div>

                        {/* Active toggle */}
                        <label className="flex items-center gap-2 py-1 mb-4 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={isActive}
                                onChange={(e) => setIsActive(e.target.checked)}
                                className="rounded border-slate-300"
                            />
                            <span className="text-sm text-slate-700">Template active</span>
                            <span className="text-xs text-slate-500">— bot uses it for daily drafts</span>
                        </label>

                        {/* Footer */}
                        <div className="flex gap-2 pt-4 border-t border-slate-200">
                            {/* Delete (only if a template exists) */}
                            {hasExistingTemplate && (
                                <button
                                    type="button"
                                    onClick={() => setDeleteConfirmOpen(true)}
                                    disabled={isSubmitting}
                                    className="py-2 px-3 text-sm text-red-600 hover:text-red-700 disabled:opacity-50"
                                >
                                    Delete template
                                </button>
                            )}
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
                                onClick={handleSave}
                                disabled={isSubmitting}
                                className="flex-1 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white rounded-lg font-medium"
                            >
                                {isSubmitting ? 'Saving…' : 'Save template'}
                            </button>
                        </div>
                    </>
                )}

                {/* Delete confirmation */}
                <ConfirmDialog
                    open={deleteConfirmOpen}
                    title="Delete default order template?"
                    message={
                        customer
                            ? `${customer.name}'s default order template will be removed entirely. You can recreate it any time.`
                            : ''
                    }
                    confirmLabel="Delete template"
                    destructive
                    isProcessing={deleteMut.isPending}
                    onConfirm={handleDeleteConfirm}
                    onCancel={() => setDeleteConfirmOpen(false)}
                />
            </div>
        </div>
    );
}