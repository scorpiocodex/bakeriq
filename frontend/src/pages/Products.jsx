/**
 * Products page — list, filter by category and availability, search,
 * add/edit, deactivate, reactivate.
 *
 * Layout matches the Customers page (consistency = predictability):
 *   - Header strip (title + count + add button)
 *   - Filter card (category chips, availability filter, search input)
 *   - Data table (or empty state / loading state / error state)
 *
 * Two modals overlay this page when needed:
 *   - ProductFormModal (create or edit)
 *   - ConfirmDialog (deactivation)
 *
 * The category filter chips are dynamic — we build them from the
 * categories API response, so adding a new category via the form
 * modal makes a chip appear here automatically (after cache invalidation).
 */
import { useState } from 'react';

import ConfirmDialog from '../components/ConfirmDialog';
import ProductFormModal from '../components/ProductFormModal';
import { useCategoriesList } from '../hooks/useCategories';
import {
    useDeactivateProduct,
    useProductsList,
    useUpdateProduct,
} from '../hooks/useProducts';

// Status filter — three discrete states matching the customer page pattern.
const STATUS_FILTERS = [
    { key: 'active', label: 'Active' },
    { key: 'inactive', label: 'Inactive' },
];

// Build the API filter params from current UI state.
function buildFilterParams({ activeStatus, categoryId, availableOnly, search }) {
    const params = { status: activeStatus };
    if (categoryId) params.categoryId = categoryId;
    if (availableOnly) params.availableToday = true;
    if (search.trim()) params.search = search.trim();
    return params;
}

// Render the price as ₹ with two decimals. unit_price comes back as a
// string from JSON serialisation of Decimal — Number() coerces safely.
function formatPrice(price, unitLabel) {
    const num = Number(price);
    if (Number.isNaN(num)) return '—';
    return `₹${num.toFixed(2)} / ${unitLabel}`;
}

// =============================================================================
// The page
// =============================================================================
export default function Products() {
    // ---- UI state ----
    const [activeStatus, setActiveStatus] = useState('active');
    const [activeCategoryId, setActiveCategoryId] = useState(null);  // null = "All"
    const [availableOnly, setAvailableOnly] = useState(false);
    const [search, setSearch] = useState('');

    // Modal state
    const [modalOpen, setModalOpen] = useState(false);
    const [modalMode, setModalMode] = useState('create');
    const [editingProduct, setEditingProduct] = useState(null);
    const [deactivateTarget, setDeactivateTarget] = useState(null);

    // ---- Server state ----
    const queryFilters = buildFilterParams({
        activeStatus,
        categoryId: activeCategoryId,
        availableOnly,
        search,
    });

    const { data, isLoading, isError, error } = useProductsList(queryFilters);
    const categoriesQuery = useCategoriesList({ status: 'active', limit: 100 });
    const deactivateMut = useDeactivateProduct();
    const updateMut = useUpdateProduct();

    // ---- Handlers ----
    function openCreate() {
        setModalMode('create');
        setEditingProduct(null);
        setModalOpen(true);
    }

    function openEdit(product) {
        setModalMode('edit');
        setEditingProduct(product);
        setModalOpen(true);
    }

    async function handleDeactivateConfirm() {
        if (!deactivateTarget) return;
        try {
            await deactivateMut.mutateAsync(deactivateTarget.id);
        } catch {
            // Mutation error captured in deactivateMut.error if needed.
        } finally {
            setDeactivateTarget(null);
        }
    }

    // Reactivate is a single-click action — no confirmation. Same pattern
    // as customers: deactivation is destructive (red, confirmed); reactivation
    // is recovery (green, instant).
    async function handleReactivate(product) {
        try {
            await updateMut.mutateAsync({
                id: product.id,
                payload: { is_active: true },
            });
        } catch {
            // Failure visible because product stays in the inactive filter
        }
    }

    // Inline toggle of is_available_today directly from a row's chip.
    // Saves a click vs opening the edit modal just to flip one boolean.
    async function handleToggleAvailable(product) {
        try {
            await updateMut.mutateAsync({
                id: product.id,
                payload: { is_available_today: !product.is_available_today },
            });
        } catch {
            // Failure visible because the chip stays the previous colour
        }
    }

    // Defaults for when data is undefined (still loading / errored)
    const products = data?.items ?? [];
    const total = data?.total ?? 0;
    const categories = categoriesQuery.data?.items ?? [];

    return (
        <>
            {/* === Page header strip === */}
            <div className="flex items-center justify-between mb-3">
                <div>
                    <p className="text-sm font-medium text-slate-900">Products</p>
                    <p className="text-xs text-slate-500">
                        {isLoading
                            ? 'Loading…'
                            : `${total} product${total === 1 ? '' : 's'}${search ? ` matching "${search}"` : ''
                            }`}
                    </p>
                </div>
                <button
                    onClick={openCreate}
                    className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
                >
                    + Add product
                </button>
            </div>

            {/* === Filter card === */}
            <div className="bg-white border border-slate-200 rounded-lg p-2.5 mb-2.5 space-y-2">
                {/* Row 1: Status + Available toggle + Search */}
                <div className="flex flex-wrap items-center gap-2">
                    {STATUS_FILTERS.map((f) => (
                        <button
                            key={f.key}
                            onClick={() => setActiveStatus(f.key)}
                            className={`text-xs px-3 py-1 rounded-full border ${activeStatus === f.key
                                ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
                                }`}
                        >
                            {f.label}
                        </button>
                    ))}

                    <span className="text-slate-300">|</span>

                    <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={availableOnly}
                            onChange={(e) => setAvailableOnly(e.target.checked)}
                            className="rounded border-slate-300"
                        />
                        <span className="text-xs text-slate-700">Available today only</span>
                    </label>

                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search name or description..."
                        className="ml-auto text-xs px-3 py-1 border border-slate-300 rounded-md w-56 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                    />
                </div>

                {/* Row 2: Category chips — built dynamically from categories list */}
                {categories.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-100">
                        <span className="text-xs text-slate-500 mr-1">Category:</span>
                        <button
                            onClick={() => setActiveCategoryId(null)}
                            className={`text-xs px-2.5 py-0.5 rounded-full border ${activeCategoryId === null
                                ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
                                }`}
                        >
                            All
                        </button>
                        {categories.map((c) => (
                            <button
                                key={c.id}
                                onClick={() => setActiveCategoryId(c.id)}
                                className={`text-xs px-2.5 py-0.5 rounded-full border ${activeCategoryId === c.id
                                    ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                                    : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
                                    }`}
                            >
                                {c.name}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* === Products table === */}
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
                            <th className="px-3 py-2 font-medium">Product</th>
                            <th className="px-3 py-2 font-medium">Category</th>
                            <th className="px-3 py-2 font-medium">Price</th>
                            <th className="px-3 py-2 font-medium">Available today</th>
                            <th className="px-3 py-2 font-medium">Status</th>
                            <th className="px-3 py-2 font-medium text-right"></th>
                        </tr>
                    </thead>
                    <tbody className="text-slate-900">
                        {/* Loading state */}
                        {isLoading && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                    Loading products…
                                </td>
                            </tr>
                        )}

                        {/* Error state */}
                        {isError && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-red-700">
                                    Could not load products: {error?.message ?? 'unknown error'}
                                </td>
                            </tr>
                        )}

                        {/* Empty state */}
                        {!isLoading && !isError && products.length === 0 && (
                            <tr>
                                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                    {search || activeCategoryId || availableOnly || activeStatus !== 'active'
                                        ? 'No products match your filters.'
                                        : 'No products yet. Click "+ Add product" to create the first one.'}
                                </td>
                            </tr>
                        )}

                        {/* Product rows */}
                        {products.map((p) => (
                            <tr key={p.id} className="border-b border-slate-100 last:border-b-0">
                                {/* Name + description preview */}
                                <td className="px-3 py-2.5">
                                    <div className="font-medium">{p.name}</div>
                                    {p.description && (
                                        <div className="text-[11px] text-slate-500 truncate max-w-md">
                                            {p.description}
                                        </div>
                                    )}
                                </td>

                                {/* Category chip */}
                                <td className="px-3 py-2.5">
                                    <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                                        {p.category?.name ?? '—'}
                                    </span>
                                </td>

                                {/* Price (monospaced for column alignment) */}
                                <td className="px-3 py-2.5 font-mono text-[11px] text-slate-700">
                                    {formatPrice(p.unit_price, p.unit_label)}
                                </td>

                                {/* Available today — clickable chip toggles availability */}
                                <td className="px-3 py-2.5">
                                    <button
                                        onClick={() => handleToggleAvailable(p)}
                                        disabled={updateMut.isPending || !p.is_active}
                                        className={`text-[10px] px-2 py-0.5 rounded transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${p.is_available_today
                                            ? 'bg-teal-100 text-teal-800 hover:bg-teal-200'
                                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                            }`}
                                    >
                                        {p.is_available_today ? 'Yes' : 'No'}
                                    </button>
                                </td>

                                {/* Active/inactive status chip */}
                                <td className="px-3 py-2.5">
                                    {p.is_active ? (
                                        <span className="text-[10px] px-2 py-0.5 bg-green-100 text-green-800 rounded">
                                            Active
                                        </span>
                                    ) : (
                                        <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                                            Inactive
                                        </span>
                                    )}
                                </td>

                                {/* Actions */}
                                <td className="px-3 py-2.5 text-right">
                                    <button
                                        onClick={() => openEdit(p)}
                                        className="text-brand-600 hover:text-brand-700 text-xs mr-3"
                                    >
                                        Edit
                                    </button>
                                    {p.is_active ? (
                                        <button
                                            onClick={() => setDeactivateTarget(p)}
                                            className="text-red-600 hover:text-red-700 text-xs"
                                        >
                                            Deactivate
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleReactivate(p)}
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

            {/* === Modals === */}
            <ProductFormModal
                open={modalOpen}
                mode={modalMode}
                product={editingProduct}
                onClose={() => setModalOpen(false)}
            />

            <ConfirmDialog
                open={deactivateTarget !== null}
                title="Deactivate product?"
                message={
                    deactivateTarget
                        ? `${deactivateTarget.name} will no longer appear in the active products list. Order history is preserved and the product can be reactivated later.`
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