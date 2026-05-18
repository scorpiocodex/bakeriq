/**
 * Settings page — currently houses Category management.
 *
 * Future sections (Phase 6+):
 *   - Bakery info (name, owner, business hours)
 *   - Notification preferences
 *   - Bot configuration
 *   - User management
 *
 * For now, just Categories. Layout has a top-level page header and
 * a card-per-section pattern that future sections will follow.
 */
import { useState } from 'react';

import ConfirmDialog from '../components/ConfirmDialog';
import {
    useCategoriesList,
    useCreateCategory,
    useDeactivateCategory,
    useHardDeleteCategory,
    useUpdateCategory,
} from '../hooks/useCategories';

export default function Settings() {
    return (
        <>
            {/* === Page header === */}
            <div className="mb-3">
                <p className="text-sm font-medium text-slate-900">Settings</p>
                <p className="text-xs text-slate-500">
                    Configure how BakeriQ works for your bakery
                </p>
            </div>

            {/* === Categories section === */}
            <CategoriesSection />

            {/* Placeholder for future sections — empty state for now */}
            <div className="bg-white border border-slate-200 rounded-lg p-4 mt-3 text-center text-xs text-slate-400">
                More settings coming in Phase 6 — bakery info, notifications,
                bot configuration.
            </div>
        </>
    );
}

// =============================================================================
// CategoriesSection — manage the product category taxonomy
// =============================================================================
function CategoriesSection() {
    const [showInactive, setShowInactive] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [editingName, setEditingName] = useState('');
    const [editingDisplayOrder, setEditingDisplayOrder] = useState(0);
    const [deactivateTarget, setDeactivateTarget] = useState(null);
    const [hardDeleteTarget, setHardDeleteTarget] = useState(null);

    // Add-new-category inline form
    const [newName, setNewName] = useState('');
    const [newError, setNewError] = useState('');

    const queryFilters = showInactive
        ? { status: 'all', limit: 100 }
        : { status: 'active', limit: 100 };

    const { data, isLoading, isError, error } = useCategoriesList(queryFilters);
    const createMut = useCreateCategory();
    const updateMut = useUpdateCategory();
    const deactivateMut = useDeactivateCategory();
    const hardDeleteMut = useHardDeleteCategory();

    const categories = data?.items ?? [];

    // === Handlers ===
    async function handleAddCategory(e) {
        e.preventDefault();
        setNewError('');
        if (!newName.trim()) {
            setNewError('Category name is required.');
            return;
        }
        try {
            await createMut.mutateAsync({
                name: newName,
                display_order: 0,
            });
            setNewName('');
        } catch (err) {
            const detail = err.response?.data?.detail;
            setNewError(typeof detail === 'string' ? detail : 'Could not add category.');
        }
    }

    function startEditing(category) {
        setEditingId(category.id);
        setEditingName(category.name);
        setEditingDisplayOrder(category.display_order);
    }

    function cancelEditing() {
        setEditingId(null);
        setEditingName('');
        setEditingDisplayOrder(0);
    }

    async function saveEdit() {
        if (!editingId) return;
        try {
            await updateMut.mutateAsync({
                id: editingId,
                payload: {
                    name: editingName,
                    display_order: Number(editingDisplayOrder),
                },
            });
            cancelEditing();
        } catch (err) {
            const detail = err.response?.data?.detail;
            alert(typeof detail === 'string' ? detail : 'Could not update category.');
        }
    }

    async function handleDeactivateConfirm() {
        if (!deactivateTarget) return;
        try {
            await deactivateMut.mutateAsync(deactivateTarget.id);
        } catch {
            // Stays visible since list refetch fails
        } finally {
            setDeactivateTarget(null);
        }
    }

    async function handleReactivate(category) {
        try {
            await updateMut.mutateAsync({
                id: category.id,
                payload: { is_active: true },
            });
        } catch {
            // Failure visible because row stays inactive
        }
    }

    async function handleHardDeleteConfirm() {
        if (!hardDeleteTarget) return;
        try {
            await hardDeleteMut.mutateAsync(hardDeleteTarget.id);
        } catch (err) {
            const detail = err.response?.data?.detail;
            alert(
                typeof detail === 'string'
                    ? detail
                    : 'Could not permanently delete category.'
            );
        } finally {
            setHardDeleteTarget(null);
        }
    }

    return (
        <div className="bg-white border border-slate-200 rounded-lg p-4">
            {/* Section header */}
            <div className="flex items-center justify-between mb-3">
                <div>
                    <p className="text-sm font-medium text-slate-900">Categories</p>
                    <p className="text-xs text-slate-500">
                        Group products into categories. Used in product forms and filters.
                    </p>
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={showInactive}
                        onChange={(e) => setShowInactive(e.target.checked)}
                        className="rounded border-slate-300"
                    />
                    <span className="text-xs text-slate-700">Show inactive</span>
                </label>
            </div>

            {/* Add new category — compact inline form */}
            <form onSubmit={handleAddCategory} className="flex items-center gap-2 mb-4 pb-4 border-b border-slate-100">
                <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="New category name..."
                    className="flex-1 text-xs px-3 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                />
                <button
                    type="submit"
                    disabled={createMut.isPending}
                    className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white rounded-md font-medium"
                >
                    + Add
                </button>
            </form>

            {newError && (
                <div role="alert" className="bg-red-50 border border-red-200 text-red-800 text-xs px-3 py-2 rounded-lg mb-3">
                    {newError}
                </div>
            )}

            {/* Loading/error/empty/table */}
            {isLoading && (
                <p className="text-xs text-slate-500 py-4 text-center">Loading categories…</p>
            )}

            {isError && (
                <p className="text-xs text-red-700 py-4 text-center">
                    Could not load categories: {error?.message ?? 'unknown error'}
                </p>
            )}

            {!isLoading && !isError && categories.length === 0 && (
                <p className="text-xs text-slate-500 py-4 text-center">
                    No categories yet. Add the first one above.
                </p>
            )}

            {/* Categories list — each is a compact row, edit-in-place */}
            {categories.length > 0 && (
                <ul className="space-y-1">
                    {categories.map((c) => (
                        <li
                            key={c.id}
                            className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-lg hover:bg-slate-50"
                        >
                            {editingId === c.id ? (
                                // === Edit mode ===
                                <>
                                    <input
                                        type="text"
                                        value={editingName}
                                        onChange={(e) => setEditingName(e.target.value)}
                                        className="flex-1 text-xs px-2 py-1 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                                        autoFocus
                                    />
                                    <label className="text-xs text-slate-500">Order:</label>
                                    <input
                                        type="number"
                                        min="0"
                                        max="9999"
                                        value={editingDisplayOrder}
                                        onChange={(e) => setEditingDisplayOrder(e.target.value)}
                                        className="w-16 text-xs px-2 py-1 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                                    />
                                    <button
                                        onClick={saveEdit}
                                        disabled={updateMut.isPending}
                                        className="text-xs px-2 py-1 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white rounded font-medium"
                                    >
                                        Save
                                    </button>
                                    <button
                                        onClick={cancelEditing}
                                        disabled={updateMut.isPending}
                                        className="text-xs px-2 py-1 text-slate-600 hover:text-slate-800"
                                    >
                                        Cancel
                                    </button>
                                </>
                            ) : (
                                // === Display mode ===
                                <>
                                    <span className="flex-1 text-sm text-slate-900">{c.name}</span>
                                    <span className="text-[10px] text-slate-400">order: {c.display_order}</span>

                                    {c.is_active ? (
                                        <span className="text-[10px] px-2 py-0.5 bg-green-100 text-green-800 rounded">
                                            Active
                                        </span>
                                    ) : (
                                        <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                                            Inactive
                                        </span>
                                    )}

                                    <button
                                        onClick={() => startEditing(c)}
                                        className="text-xs text-brand-600 hover:text-brand-700 ml-1"
                                    >
                                        Edit
                                    </button>

                                    {c.is_active ? (
                                        <button
                                            onClick={() => setDeactivateTarget(c)}
                                            className="text-xs text-red-600 hover:text-red-700"
                                        >
                                            Deactivate
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => handleReactivate(c)}
                                            disabled={updateMut.isPending}
                                            className="text-xs text-green-700 hover:text-green-800 disabled:opacity-50"
                                        >
                                            Reactivate
                                        </button>
                                    )}

                                    {/* Hard-delete only offered when category is already inactive
                      — encourages soft-delete as the default path */}
                                    {!c.is_active && (
                                        <button
                                            onClick={() => setHardDeleteTarget(c)}
                                            className="text-xs text-red-700 hover:text-red-900"
                                            title="Permanently delete (only if no products reference it)"
                                        >
                                            Delete
                                        </button>
                                    )}
                                </>
                            )}
                        </li>
                    ))}
                </ul>
            )}

            {/* Deactivate confirmation */}
            <ConfirmDialog
                open={deactivateTarget !== null}
                title="Deactivate category?"
                message={
                    deactivateTarget
                        ? `"${deactivateTarget.name}" will no longer appear in the category dropdown when adding products. Existing products in this category keep their reference. Reactivate any time.`
                        : ''
                }
                confirmLabel="Deactivate"
                destructive
                isProcessing={deactivateMut.isPending}
                onConfirm={handleDeactivateConfirm}
                onCancel={() => setDeactivateTarget(null)}
            />

            {/* Hard-delete confirmation — different wording, more dire */}
            <ConfirmDialog
                open={hardDeleteTarget !== null}
                title="Permanently delete category?"
                message={
                    hardDeleteTarget
                        ? `"${hardDeleteTarget.name}" will be deleted from the database entirely. This will fail if any products (active or inactive) reference this category — you'll need to reassign or deactivate those products first. This action cannot be undone.`
                        : ''
                }
                confirmLabel="Delete permanently"
                destructive
                isProcessing={hardDeleteMut.isPending}
                onConfirm={handleHardDeleteConfirm}
                onCancel={() => setHardDeleteTarget(null)}
            />
        </div>
    );
}