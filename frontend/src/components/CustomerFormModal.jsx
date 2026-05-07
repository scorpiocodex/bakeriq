/**
 * Modal form for creating or editing a customer.
 *
 * Used in two modes from the same component:
 *   mode="create" — empty form, calls useCreateCustomer on submit
 *   mode="edit"   — pre-filled with customer data, calls useUpdateCustomer
 *
 * Layout: two visual sections separated by a labelled divider:
 *   1. Contact info (name, phones, preferences, WhatsApp toggle)
 *   2. Address (5 fields in Indian postal format)
 *   3. Notes
 *
 * The sectioning is purely visual — internally it's still one form.
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
    address_line_1: '',
    address_line_2: '',
    city: '',
    state: 'Kerala', // Default for the bakery's home state — saves typing in 95% of cases
    pincode: '',
    notes: '',
};

export default function CustomerFormModal({ open, mode, customer, onClose }) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [error, setError] = useState('');

    const createMut = useCreateCustomer();
    const updateMut = useUpdateCustomer();
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
                address_line_1: customer.address_line_1 ?? '',
                address_line_2: customer.address_line_2 ?? '',
                city: customer.city ?? '',
                state: customer.state ?? 'Kerala',
                pincode: customer.pincode ?? '',
                notes: customer.notes ?? '',
            });
        } else {
            setForm(EMPTY_FORM);
        }
        setError('');
    }, [open, mode, customer]);

    if (!open) return null;

    function handleChange(field, value) {
        setForm((f) => ({ ...f, [field]: value }));
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError('');

        // Build the payload from form state. Required fields go in directly;
        // optional fields are dropped entirely if blank, so the backend stores
        // null rather than empty string "".
        const payload = {
            name: form.name.trim(),
            primary_phone: form.primary_phone.trim(),
            preferred_channel_phone: form.preferred_channel_phone,
            whatsapp_enabled: form.whatsapp_enabled,
            address_line_1: form.address_line_1.trim(),
            city: form.city.trim(),
            state: form.state.trim(),
            pincode: form.pincode.trim(),
        };
        if (form.secondary_phone.trim()) payload.secondary_phone = form.secondary_phone.trim();
        if (form.address_line_2.trim()) payload.address_line_2 = form.address_line_2.trim();
        if (form.notes.trim()) payload.notes = form.notes.trim();

        try {
            if (mode === 'edit') {
                await updateMut.mutateAsync({ id: customer.id, payload });
            } else {
                await createMut.mutateAsync(payload);
            }
            onClose();
        } catch (err) {
            // FastAPI puts the user-facing error message in response.data.detail.
            // For 409 it's a string; for 422 it's an array of error objects.
            // Fall back to a generic message for the array case.
            const detail = err.response?.data?.detail;
            setError(typeof detail === 'string' ? detail : 'Could not save customer. Please check the form and try again.');
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
        Wider modal (max-w-lg vs original max-w-md) to accommodate the
        address grid. Also scrolls vertically if the form gets too tall
        on small screens (max-h-[90vh] + overflow-y-auto).
      */}
            <form
                onSubmit={handleSubmit}
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto"
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

                {/* === Section 1: Contact info === */}
                <div className="space-y-3 mb-5">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Contact info
                    </p>

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
                </div>

                {/* === Section 2: Address (5 fields in Indian postal format) === */}
                <div className="space-y-3 mb-5 pt-4 border-t border-slate-200">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Address
                    </p>

                    {/* Line 1 (required) */}
                    <div>
                        <label htmlFor="cf-addr-1" className="block text-sm text-slate-700 mb-1">
                            Address line 1 <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="cf-addr-1"
                            type="text"
                            required
                            value={form.address_line_1}
                            onChange={(e) => handleChange('address_line_1', e.target.value)}
                            placeholder="Building/house name, door number"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* Line 2 (optional) */}
                    <div>
                        <label htmlFor="cf-addr-2" className="block text-sm text-slate-700 mb-1">
                            Address line 2 <span className="text-slate-400">(optional)</span>
                        </label>
                        <input
                            id="cf-addr-2"
                            type="text"
                            value={form.address_line_2}
                            onChange={(e) => handleChange('address_line_2', e.target.value)}
                            placeholder="Post office, locality, landmark"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* City + State row — two-column grid for compactness */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="cf-city" className="block text-sm text-slate-700 mb-1">
                                City <span className="text-red-600">*</span>
                            </label>
                            <input
                                id="cf-city"
                                type="text"
                                required
                                value={form.city}
                                onChange={(e) => handleChange('city', e.target.value)}
                                placeholder="Ernakulam"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />
                        </div>
                        <div>
                            <label htmlFor="cf-state" className="block text-sm text-slate-700 mb-1">
                                State <span className="text-red-600">*</span>
                            </label>
                            <input
                                id="cf-state"
                                type="text"
                                required
                                value={form.state}
                                onChange={(e) => handleChange('state', e.target.value)}
                                placeholder="Kerala"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />
                        </div>
                    </div>

                    {/* PIN code (required, 6 digits) */}
                    <div>
                        <label htmlFor="cf-pincode" className="block text-sm text-slate-700 mb-1">
                            PIN code <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="cf-pincode"
                            type="text"
                            required
                            value={form.pincode}
                            onChange={(e) => handleChange('pincode', e.target.value)}
                            placeholder="682001"
                            maxLength={7}  /* allows space if user types "682 001"; backend strips it */
                            inputMode="numeric"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 font-mono"
                        />
                        <p className="text-xs text-slate-500 mt-1">6 digits</p>
                    </div>
                </div>

                {/* === Section 3: Notes === */}
                <div className="space-y-3 mb-5 pt-4 border-t border-slate-200">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Notes
                    </p>
                    <textarea
                        rows={2}
                        value={form.notes}
                        onChange={(e) => handleChange('notes', e.target.value)}
                        placeholder="Daily customer, prefers extra crispy puffs"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 resize-none"
                    />
                </div>

                {/* Footer with Cancel and Save buttons */}
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