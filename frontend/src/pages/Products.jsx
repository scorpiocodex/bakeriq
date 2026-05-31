/**
 * Products page — list, filter by status + category, add, edit, deactivate.
 *
 * Layout matches the BakeriQ design system:
 *   - Header strip (title + count + add button)
 *   - Filter card (status chips + category chips + "available today only")
 *   - Data table with status badge + actions menu
 */
import { useState } from 'react';
import ConfirmDialog from '../components/ConfirmDialog';
import ProductFormModal from '../components/ProductFormModal';
import RowActionsMenu from '../components/RowActionsMenu';
import StatusBadge from '../components/StatusBadge';
import { useCategoriesList } from '../hooks/useCategories';
import { useDeactivateProduct, useProductsList, useUpdateProduct } from '../hooks/useProducts';

const STATUS_FILTERS = [
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Inactive' },
];

export default function Products() {
  const [activeStatus, setActiveStatus] = useState('active');
  const [activeCategoryId, setActiveCategoryId] = useState(null);
  const [availableTodayOnly, setAvailableTodayOnly] = useState(false);
  const [search, setSearch] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [editingProduct, setEditingProduct] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const queryFilters = {
    status: activeStatus,
    categoryId: activeCategoryId,
    availableTodayOnly: availableTodayOnly || null,
    search: search.trim() || null,
    limit: 100,
  };

  const { data, isLoading, isError, error } = useProductsList(queryFilters);
  const categoriesQuery = useCategoriesList({ status: 'active', limit: 100 });
  const deactivateMut = useDeactivateProduct();
  const updateMut = useUpdateProduct();

  const products = data?.items ?? [];
  const total = data?.total ?? 0;
  const categories = categoriesQuery.data?.items ?? [];

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
      // Stays visible if list refetch fails
    } finally {
      setDeactivateTarget(null);
    }
  }

  async function handleReactivate(product) {
    try {
      await updateMut.mutateAsync({
        id: product.id,
        payload: { is_active: true },
      });
    } catch {
      // Row stays inactive — visible feedback
    }
  }

  return (
    <>
      {/* Page header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-slate-900">Products</p>
          <p className="text-xs text-slate-500">
            {isLoading
              ? 'Loading…'
              : `${total} product${total === 1 ? '' : 's'}${search ? ` matching "${search}"` : ''}`}
          </p>
        </div>
        <button
          onClick={openCreate}
          className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
        >
          + Add product
        </button>
      </div>

      {/* Filter card */}
      <div className="bg-white border border-slate-200 rounded-lg p-2.5 mb-2.5 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setActiveStatus(f.key)}
              className={`text-xs px-3 py-1 rounded-full border ${
                activeStatus === f.key
                  ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {f.label}
            </button>
          ))}

          <label className="flex items-center gap-1.5 ml-2 cursor-pointer">
            <input
              type="checkbox"
              checked={availableTodayOnly}
              onChange={(e) => setAvailableTodayOnly(e.target.checked)}
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

        {/* Category chips */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-100">
          <span className="text-xs text-slate-500 mr-1">Category:</span>
          <button
            onClick={() => setActiveCategoryId(null)}
            className={`text-xs px-3 py-1 rounded-full border ${
              activeCategoryId === null
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
              className={`text-xs px-3 py-1 rounded-full border ${
                activeCategoryId === c.id
                  ? 'bg-brand-50 text-brand-700 border-brand-300 font-medium'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
              <th className="px-3 py-2 font-medium">Product</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Price</th>
              <th className="px-3 py-2 font-medium">Available today</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="text-slate-900">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  Loading products…
                </td>
              </tr>
            )}

            {isError && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-red-700">
                  Could not load products: {error?.message ?? 'unknown error'}
                </td>
              </tr>
            )}

            {!isLoading && !isError && products.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  {search || activeCategoryId || availableTodayOnly
                    ? 'No products match your filters.'
                    : 'No products yet. Click "+ Add product" to create the first one.'}
                </td>
              </tr>
            )}

            {products.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 last:border-b-0">
                <td className="px-3 py-2.5">
                  <div className="font-medium">{p.name}</div>
                  {p.description && (
                    <div className="text-[11px] text-slate-500">{p.description}</div>
                  )}
                </td>

                <td className="px-3 py-2.5">
                  {p.category ? (
                    <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                      {p.category.name}
                    </span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>

                <td className="px-3 py-2.5 font-mono text-slate-700">
                  ₹{Number(p.unit_price).toFixed(2)} / {p.unit_label}
                </td>

                <td className="px-3 py-2.5">
                  {p.is_available_today ? (
                    <span className="text-[10px] px-2 py-0.5 bg-green-100 text-green-800 rounded">
                      Yes
                    </span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                      No
                    </span>
                  )}
                </td>

                {/* Active/inactive status chip */}
                <td className="px-3 py-2.5">
                  <StatusBadge status={p.is_active ? 'active' : 'inactive'} size="xs" />
                </td>

                {/* Actions menu */}
                <td className="px-3 py-2.5 text-right">
                  <RowActionsMenu
                    actions={[
                      { label: 'Edit', onClick: () => openEdit(p) },
                      p.is_active
                        ? {
                            label: 'Deactivate',
                            destructive: true,
                            onClick: () => setDeactivateTarget(p),
                          }
                        : {
                            label: 'Reactivate',
                            disabled: updateMut.isPending,
                            onClick: () => handleReactivate(p),
                          },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modals */}
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
            ? `"${deactivateTarget.name}" will no longer appear in the active product list. Order history that references this product is preserved (snapshots). Reactivate any time.`
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
