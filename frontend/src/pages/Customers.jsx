/**
 * Customers page — list, search, filter, add, edit, deactivate, reactivate.
 *
 * Layout matches the BakeriQ design system:
 *   - Header strip (title + count + add button)
 *   - Filter card (chips + search input)
 *   - Data table (or empty state / loading state / error state)
 *
 * Two modals overlay this page when needed:
 *   - CustomerFormModal (create or edit)
 *   - ConfirmDialog (deactivation)
 *
 * State is split between server-state (in TanStack Query cache, accessed
 * via hooks) and UI-state (in this component's useState). The split:
 *   server: customer list, individual customer details
 *   UI: which filter chip is active, what's in the search box, which
 *       modal is open, which customer is the deactivation target
 */
import { useState } from 'react';
import ConfirmDialog from '../components/ConfirmDialog';
import CustomerFormModal from '../components/CustomerFormModal';
import {
    useCustomersList,
    useDeactivateCustomer,
    useUpdateCustomer,
} from '../hooks/useCustomers';

// =============================================================================
// Filter chip definitions — adding a new chip is one entry here.
// =============================================================================
const FILTERS = [
    { key: 'all', label: 'All' },
    { key: 'whatsapp', label: 'WhatsApp' },
    { key: 'voice', label: 'Voice only' },
    { key: 'inactive', label: 'Inactive' },
];

// Translates the chip selection into API filter params.
//
// "All" chip means "all active customers" (NOT "everything including inactive")
// because that's what the user expects from a default view. The Inactive chip
// is the only path to seeing deactivated customers.
function buildFilterParams(filterKey) {
    switch (filterKey) {
        case 'whatsapp':
            return { whatsappOnly: true, status: 'active' };
        case 'voice':
            return { whatsappOnly: false, status: 'active' };
        case 'inactive':
            return { whatsappOnly: null, status: 'inactive' };
        case 'all':
        default:
            return { whatsappOnly: null, status: 'active' };
    }
}
// Customer initials for the avatar circle. Same logic as TopBar's
// initials helper. Could be extracted to a shared util later.
function getInitials(name) {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// =============================================================================
// The page
// =============================================================================
export default function Customers() {
    // ---- UI state ----
    // Which filter chip is selected — drives the API query
    const [activeFilter, setActiveFilter] = useState('all');
    // Live search input — also drives the API query, debouncing not needed
    // at this scale because the response interceptor in client.js dedupes
    // and TanStack Query caches identical-key queries
    const [search, setSearch] = useState('');

    // Modal state — three independent slots:
    //   1. Form modal open + mode (create/edit) + which customer to edit
    //   2. Deactivate confirmation: which customer is the target (null = closed)
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState('create');
    const [editingCustomer, setEditingCustomer] = useState(null);
    const [deactivateTarget, setDeactivateTarget] = useState(null);

    // ---- Server state (via TanStack Query) ----
    const filterParams = buildFilterParams(activeFilter);
    // search.trim() || null — converts empty string to null so the API client
    // omits the param entirely (vs. sending ?search= which the backend would
    // treat as "name contains empty string")
    const queryFilters = { ...filterParams, search: search.trim() || null };

    const { data, isLoading, isError, error } = useCustomersList(queryFilters);
    const deactivateMut = useDeactivateCustomer();
    // updateMut serves two purposes: editing customer fields (via the form modal)
    // and reactivating inactive customers (via the inline Reactivate button).
    // Both flows go through PUT /customers/{id} — different payload shapes only.
    const updateMut = useUpdateCustomer();

    // ---- Handlers ----
    function openCreate() {
        setModalMode('create');
        setEditingCustomer(null);
        setModalOpen(true);
    }

    function openEdit(customer) {
        setModalMode('edit');
        setEditingCustomer(customer);
        setModalOpen(true);
    }

    async function handleDeactivateConfirm() {
        if (!deactivateTarget) return;
        try {
            await deactivateMut.mutateAsync(deactivateTarget.id);
        } catch {
            // Mutation error is captured in deactivateMut.error if needed.
            // For this UX, just closing the dialog and relying on the list
            // refresh is enough — failures are rare and visible in the list.
        } finally {
            setDeactivateTarget(null);
        }
    }

    // Reactivate is a single-click action — no confirmation modal because
    // it's non-destructive (the row reappears in active filters; nothing
    // is lost). PUT with just is_active=true; backend's exclude_unset
    // handling means all other fields stay as they were.
    async function handleReactivate(customer) {
        try {
            await updateMut.mutateAsync({
                id: customer.id,
                payload: { is_active: true },
            });
        } catch {
            // Reactivation rarely fails (no validation rules involve is_active alone).
            // If it does, the row stays in the inactive filter — visible feedback.
            // Could add a toast notification here later.
        }
    }

    // Defaults for when data is undefined (still loading / errored)
    const customers = data?.items ?? [];
    const total = data?.total ?? 0;

    return (
        <>
            {/* === Page header strip === */}
            <div className="flex items-center justify-between mb-3">
                <div>
                    <p className="text-sm font-medium text-slate-900">Customers</p>
                    <p className="text-xs text-slate-500">
                        {isLoading
                            ? 'Loading…'
                            : `${total} customer${total === 1 ? '' : 's'}${search ? ` matching "${search}"` : ''
                            }`}
                    </p>
                </div>
                <button
                    onClick={openCreate}
                    className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
                >
                    + Add customer
                </button>
            </div>

            {/* === Filter + search card === */}
            <div className="bg-white border border-slate-200 rounded-lg p-2.5 mb-2.5">
                <div className="flex flex-wrap items-center gap-2">
                    {FILTERS.map((f) => (
                        <button
                            key={f.key}
                            onClick={() => setActiveFilter(f.key)}
                            className={`text-xs px-3 py-1 rounded-full border ${activeFilter === f.key
                                ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
                                }`}
                        >
                            {f.label}
                        </button>
                    ))}
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search name or phone..."
                        className="ml-auto text-xs px-3 py-1 border border-slate-300 rounded-md w-48 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                    />
                </div>
            </div>

            {/* === Customers table === */}
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
                            <th className="px-3 py-2 font-medium">Customer</th>
                            <th className="px-3 py-2 font-medium">Primary phone</th>
                            <th className="px-3 py-2 font-medium">Secondary</th>
                            <th className="px-3 py-2 font-medium">Channel</th>
                            <th className="px-3 py-2 font-medium">Status</th>
                            <th className="px-3 py-2 font-medium text-right"></th>
                        </tr>
                    </thead>
                    <tbody className="text-slate-900">
                        {/* Loading state — first load only (subsequent fetches keep previous data) */}
                        {isLoading && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                    Loading customers…
                                </td>
                            </tr>
                        )}

                        {/* Error state */}
                        {isError && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-red-700">
                                    Could not load customers: {error?.message ?? 'unknown error'}
                                </td>
                            </tr>
                        )}

                        {/* Empty state — different message depending on whether filters are active */}
                        {!isLoading && !isError && customers.length === 0 && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                    {search || activeFilter !== 'all'
                                        ? 'No customers match your filters.'
                                        : 'No customers yet. Click "+ Add customer" to create the first one.'}
                                </td>
                            </tr>
                        )}

                        {/* Customer rows */}
                        {customers.map((c) => (
                            <tr key={c.id} className="border-b border-slate-100 last:border-b-0">
                                {/* Name with avatar */}
                                <td className="px-3 py-2.5">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-[10px] font-medium flex items-center justify-center">
                                            {getInitials(c.name)}
                                        </div>
                                        <span className="font-medium">{c.name}</span>
                                    </div>
                                </td>

                                {/* Primary phone — monospaced for readability */}
                                <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">
                                    {c.primary_phone}
                                </td>

                                {/* Secondary phone — em-dash if absent */}
                                <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">
                                    {c.secondary_phone || <span className="text-slate-400">—</span>}
                                </td>

                                {/* Channel chip — teal for WhatsApp, blue for Voice */}
                                <td className="px-3 py-2.5">
                                    {c.whatsapp_enabled ? (
                                        <span className="text-[10px] px-2 py-0.5 bg-teal-100 text-teal-800 rounded">
                                            WhatsApp
                                        </span>
                                    ) : (
                                        <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-800 rounded">
                                            Voice
                                        </span>
                                    )}
                                </td>

                                {/* Active/inactive status chip */}
                                <td className="px-3 py-2.5">
                                    {c.is_active ? (
                                        <span className="text-[10px] px-2 py-0.5 bg-green-100 text-green-800 rounded">
                                            Active
                                        </span>
                                    ) : (
                                        <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                                            Inactive
                                        </span>
                                    )}
                                </td>

                                {/* Actions:
                    - Edit always available (any customer field can be changed)
                    - Active customers get red "Deactivate" (destructive)
                    - Inactive customers get green "Reactivate" (recovery, no confirm) */}
                                <td className="px-3 py-2.5 text-right">
                                    <button
                                        onClick={() => openEdit(c)}
                                        className="text-brand-600 hover:text-brand-700 text-xs mr-3"
                                    >
                                        Edit
                                    </button>
                                    {c.is_active ? (
                                        <button
                                            onClick={() => setDeactivateTarget(c)}
                                            className="text-red-600 hover:text-red-700 text-xs"
                                        >
                                            Deactivate
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleReactivate(c)}
                                            disabled={updateMut.isPending}
                                            className="text-green-700 hover:text-green-800 text-xs disabled:opacity-50"
                                        >
                                            Reactivate
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* === Modals (rendered always, controlled by `open` prop) === */}
            <CustomerFormModal
                open={modalOpen}
                mode={modalMode}
                customer={editingCustomer}
                onClose={() => setModalOpen(false)}
            />

            <ConfirmDialog
                open={deactivateTarget !== null}
                title="Deactivate customer?"
                message={
                    deactivateTarget
                        ? `${deactivateTarget.name} will no longer appear in the active customer list. Order history is preserved and the customer can be reactivated later.`
                        : ''
                }
                confirmLabel="Deactivate"
                destructive
                isProcessing={deactivateMut.isPending}
                onConfirm={handleDeactivateConfirm}
                onCancel={() => setDeactivateTarget(null)}
            />
        </>
    );
}