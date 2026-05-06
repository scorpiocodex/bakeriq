/**
 * Modal form for creating or editing a customer.
 *
 * Used in two modes from the same component:
 *   mode="create" — empty form, calls useCreateCustomer on submit
 *   mode="edit"   — pre-filled with customer data, calls useUpdateCustomer
 *
 * Why one component for both modes:
 *   The form fields are identical. The only differences (modal title,
 *   submit button label, which mutation to call) are easily handled with
 *   conditional logic. Splitting into two components would mean duplicating
 *   ~200 lines of form markup.
 */
import { useEffect, useState } from 'react';
import { useCreateCustomer, useUpdateCustomer } from '../hooks/useCustomers';

// Empty form state — used as both the create-mode initial state AND
// as the reset state when the modal closes/reopens.
const EMPTY_FORM = {
    name: '',
    primary_phone: '',
    secondary_phone: '',
    preferred_channel_phone: 'primary',
    whatsapp_enabled: false,
    address: '',
    notes: '',
};

export default function CustomerFormModal({ open, mode, customer, onClose }) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [error, setError] = useState('');

    const createMut = useCreateCustomer();
    const updateMut = useUpdateCustomer();
    // isPending (not isLoading) — TanStack v5 uses isPending for mutations
    const isSubmitting = createMut.isPending || updateMut.isPending;

    // Pre-fill the form when entering edit mode; reset when entering create mode.
    // This effect runs every time `open`, `mode`, or `customer` changes — so
    // reopening the modal with a different customer correctly re-populates,
    // and switching from edit to create properly clears the form.
    useEffect(() => {
        if (!open) return;
        if (mode === 'edit' && customer) {
            setForm({
                name: customer.name ?? '',
                primary_phone: customer.primary_phone ?? '',
                secondary_phone: customer.secondary_phone ?? '',
                preferred_channel_phone: customer.preferred_channel_phone ?? 'primary',
                whatsapp_enabled: customer.whatsapp_enabled ?? false,
                address: customer.address ?? '',
                notes: customer.notes ?? '',
            });
        } else {
            setForm(EMPTY_FORM);
        }
        setError('');
    }, [open, mode, customer]);

    // Important: we render NOTHING when not open. Without this guard, the
    // modal markup would always be in the DOM (just hidden via CSS). That
    // wastes render cycles and means inputs hold stale state between sessions.
    if (!open) return null;

    function handleChange(field, value) {
        setForm((f) => ({ ...f, [field]: value }));
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError('');

        // Build the payload from form state. Two notable transformations:
        //   1. .trim() — remove accidental leading/trailing whitespace
        //   2. Drop empty optional fields entirely so the backend stores
        //      null instead of empty string ""
        const payload = {
            name: form.name.trim(),
            primary_phone: form.primary_phone.trim(),
            preferred_channel_phone: form.preferred_channel_phone,
            whatsapp_enabled: form.whatsapp_enabled,
        };
        if (form.secondary_phone.trim()) payload.secondary_phone = form.secondary_phone.trim();
        if (form.address.trim()) payload.address = form.address.trim();
        if (form.notes.trim()) payload.notes = form.notes.trim();

        try {
            if (mode === 'edit') {
                await updateMut.mutateAsync({ id: customer.id, payload });
            } else {
                await createMut.mutateAsync(payload);
            }
            onClose();
        } catch (err) {
            // FastAPI puts the user-facing error message in response.data.detail
            // For a 409 conflict it's "Phone number +91... is already used by another customer"
            // For a 422 validation error it's an array; fall back to a generic message
            const detail = err.response?.data?.detail;
            setError(typeof detail === 'string' ? detail : 'Could not save customer. Please try again.');
        }
    }

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-modal-title"
        >
            {/*
        stopPropagation on the form — clicking inside the form shouldn't
        bubble up to the backdrop's onClose handler.
        Standard modal pattern: outside-click closes, inside-click doesn't.
      */}
            <form
                onSubmit={handleSubmit}
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-md p-6"
            >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <h2 id="customer-modal-title" className="text-base font-medium text-slate-900">
                        {mode === 'edit' ? 'Edit customer' : 'Add new customer'}
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

                {/* Error banner — shown only when error is set */}
                {error && (
                    <div role="alert" className="bg-red-50 border border-red-200 text-red-800 text-sm px-3 py-2 rounded-lg mb-4">
                        {error}
                    </div>
                )}

                <div className="space-y-3">
                    {/* Name (required) */}
                    <div>
                        <label htmlFor="cf-name" className="block text-sm text-slate-700 mb-1">
                            Name <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="cf-name"
                            type="text"
                            required
                            value={form.name}
                            onChange={(e) => handleChange('name', e.target.value)}
                            placeholder="Anita Menon"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* Primary phone (required) */}
                    <div>
                        <label htmlFor="cf-primary" className="block text-sm text-slate-700 mb-1">
                            Primary phone <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="cf-primary"
                            type="tel"
                            required
                            value={form.primary_phone}
                            onChange={(e) => handleChange('primary_phone', e.target.value)}
                            placeholder="+91 99999 12345"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                        <p className="text-xs text-slate-500 mt-1">Include country code, e.g. +91 for India</p>
                    </div>

                    {/* Secondary phone (optional) */}
                    <div>
                        <label htmlFor="cf-secondary" className="block text-sm text-slate-700 mb-1">
                            Secondary phone <span className="text-slate-400">(optional)</span>
                        </label>
                        <input
                            id="cf-secondary"
                            type="tel"
                            value={form.secondary_phone}
                            onChange={(e) => handleChange('secondary_phone', e.target.value)}
                            placeholder="+91 99999 00001"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* Preferred phone — toggle between primary/secondary */}
                    {/* Secondary button disabled when secondary_phone is empty */}
                    <div>
                        <label className="block text-sm text-slate-700 mb-1">
                            Preferred contact phone
                        </label>
                        <div className="flex gap-2">
                            <button
                                type="button"
                                onClick={() => handleChange('preferred_channel_phone', 'primary')}
                                className={`flex-1 py-2 text-sm rounded-lg border ${form.preferred_channel_phone === 'primary'
                                        ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                        : 'bg-white text-slate-600 border-slate-300'
                                    }`}
                            >
                                Primary
                            </button>
                            <button
                                type="button"
                                onClick={() => handleChange('preferred_channel_phone', 'secondary')}
                                disabled={!form.secondary_phone.trim()}
                                className={`flex-1 py-2 text-sm rounded-lg border disabled:opacity-50 disabled:cursor-not-allowed ${form.preferred_channel_phone === 'secondary'
                                        ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                        : 'bg-white text-slate-600 border-slate-300'
                                    }`}
                            >
                                Secondary
                            </button>
                        </div>
                    </div>

                    {/* WhatsApp toggle */}
                    <label className="flex items-center gap-2 py-1 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={form.whatsapp_enabled}
                            onChange={(e) => handleChange('whatsapp_enabled', e.target.checked)}
                            className="rounded border-slate-300"
                        />
                        <span className="text-sm text-slate-700">WhatsApp enabled</span>
                        <span className="text-xs text-slate-500">— bot will message instead of calling</span>
                    </label>

                    {/* Address (optional) */}
                    <div>
                        <label htmlFor="cf-address" className="block text-sm text-slate-700 mb-1">
                            Address <span className="text-slate-400">(optional)</span>
                        </label>
                        <input
                            id="cf-address"
                            type="text"
                            value={form.address}
                            onChange={(e) => handleChange('address', e.target.value)}
                            placeholder="TC 14/789, Pattom"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* Notes (optional) */}
                    <div>
                        <label htmlFor="cf-notes" className="block text-sm text-slate-700 mb-1">
                            Notes <span className="text-slate-400">(optional)</span>
                        </label>
                        <textarea
                            id="cf-notes"
                            rows={2}
                            value={form.notes}
                            onChange={(e) => handleChange('notes', e.target.value)}
                            placeholder="Daily customer, prefers extra crispy puffs"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 resize-none"
                        />
                    </div>
                </div>

                {/* Footer with Cancel and Save buttons */}
                <div className="flex gap-2 mt-5 pt-4 border-t border-slate-200">
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="flex-1 py-2 text-sm bg-white text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={isSubmitting}
                        className="flex-1 py-2 text-sm bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white rounded-lg font-medium"
                    >
                        {isSubmitting ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Add customer'}
                    </button>
                </div>
            </form>
        </div>
    );
}