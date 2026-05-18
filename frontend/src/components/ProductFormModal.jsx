/**
 * Modal form for creating or editing a product.
 *
 * Used in two modes from the same component:
 *   mode="create" — empty form, calls useCreateProduct on submit
 *   mode="edit"   — pre-filled with product data, calls useUpdateProduct
 *
 * Layout: three visual sections separated by labelled dividers:
 *   1. Basics — name, category, price, unit label
 *   2. Availability & aliases — today's availability, alias chips
 *   3. Description (optional)
 *
 * The category field is a combobox: dropdown of existing categories
 * PLUS a typed input. If the typed value doesn't match any existing
 * category, we offer "Create new: <typed value>" — which fires a POST
 * to /categories before submitting the product, all inside one
 * mutateAsync call from the user's perspective.
 */
import { useEffect, useRef, useState } from 'react';

import { useCategoriesList, useCreateCategory } from '../hooks/useCategories';
import { useCreateProduct, useUpdateProduct } from '../hooks/useProducts';

// Empty form state — used as both create-mode initial state AND
// as the reset state when the modal closes/reopens.
const EMPTY_FORM = {
    name: '',
    category_id: '',       // UUID of selected category (empty until picked)
    category_typed: '',    // The text in the combobox input (display only)
    unit_price: '',        // String for input control; coerced to number on submit
    unit_label: 'piece',
    is_available_today: true,
    aliases_text: '',      // Comma-separated string for input; parsed on submit
    description: '',
};

export default function ProductFormModal({ open, mode, product, onClose }) {
    const [form, setForm] = useState(EMPTY_FORM);
    const [error, setError] = useState('');

    // Combobox state — separate from the main form state because we
    // need to track whether the dropdown is open and which option is
    // highlighted (for keyboard navigation, though we keep that minimal).
    const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false);
    const comboboxRef = useRef(null);

    // === Hooks for API access ===
    const categoriesQuery = useCategoriesList({ status: 'active', limit: 100 });
    const createCategoryMut = useCreateCategory();
    const createProductMut = useCreateProduct();
    const updateProductMut = useUpdateProduct();

    const isSubmitting =
        createProductMut.isPending ||
        updateProductMut.isPending ||
        createCategoryMut.isPending;

    // === Effect: pre-fill on edit, reset on create ===
    // Runs when the modal opens or the customer changes. Same pattern
    // as CustomerFormModal.
    useEffect(() => {
        if (!open) return;
        if (mode === 'edit' && product) {
            setForm({
                name: product.name ?? '',
                category_id: product.category?.id ?? '',
                category_typed: product.category?.name ?? '',
                unit_price: product.unit_price?.toString() ?? '',
                unit_label: product.unit_label ?? 'piece',
                is_available_today: product.is_available_today ?? true,
                aliases_text: (product.aliases ?? []).join(', '),
                description: product.description ?? '',
            });
        } else {
            setForm(EMPTY_FORM);
        }
        setError('');
        setCategoryDropdownOpen(false);
    }, [open, mode, product]);

    // === Effect: close combobox dropdown on outside click ===
    useEffect(() => {
        function handleClickOutside(e) {
            if (comboboxRef.current && !comboboxRef.current.contains(e.target)) {
                setCategoryDropdownOpen(false);
            }
        }
        if (categoryDropdownOpen) {
            document.addEventListener('mousedown', handleClickOutside);
            return () => document.removeEventListener('mousedown', handleClickOutside);
        }
    }, [categoryDropdownOpen]);

    if (!open) return null;

    // === Helpers ===
    function handleChange(field, value) {
        setForm((f) => ({ ...f, [field]: value }));
    }

    /**
     * When the typed text matches a category exactly, select it (set id).
     * Otherwise clear the id so the submit handler knows to create new.
     */
    function handleCategoryTyped(value) {
        const normalised = value.trim().toLowerCase();
        const match = (categoriesQuery.data?.items ?? []).find(
            (c) => c.name === normalised,
        );
        setForm((f) => ({
            ...f,
            category_typed: value,
            category_id: match?.id ?? '',
        }));
    }

    /**
     * User picked an existing category from the dropdown — set both
     * the typed text and the id.
     */
    function pickExistingCategory(category) {
        setForm((f) => ({
            ...f,
            category_typed: category.name,
            category_id: category.id,
        }));
        setCategoryDropdownOpen(false);
    }

    /**
     * Parse the comma-separated aliases input into an array. Blank
     * input → empty array. The Pydantic schema does final normalisation
     * (lowercase, dedupe) so we don't have to.
     */
    function parseAliases(text) {
        return text
            .split(',')
            .map((a) => a.trim())
            .filter((a) => a.length > 0);
    }

    // === Submit ===
    async function handleSubmit(e) {
        e.preventDefault();
        setError('');

        // Step 1: resolve the category — if no existing match, create it.
        let categoryId = form.category_id;
        const typedCategory = form.category_typed.trim();

        if (!typedCategory) {
            setError('Please pick or type a category.');
            return;
        }

        if (!categoryId) {
            // No existing category matched the typed text — create one.
            try {
                const newCategory = await createCategoryMut.mutateAsync({
                    name: typedCategory,
                });
                categoryId = newCategory.id;
            } catch (err) {
                const detail = err.response?.data?.detail;
                // 409 means "category already exists" — race condition where
                // someone else created it between our list fetch and submit.
                // Fall back to a list refetch and let the user retry.
                if (err.response?.status === 409) {
                    setError(
                        `Category "${typedCategory}" already exists. Please pick it from the dropdown.`,
                    );
                    categoriesQuery.refetch();
                    return;
                }
                setError(typeof detail === 'string' ? detail : 'Could not create category.');
                return;
            }
        }

        // Step 2: build the product payload.
        // unit_price gets parsed to a Number. Blank optional fields are
        // omitted (not sent as "") so the backend stores null.
        const priceNum = Number(form.unit_price);
        if (!form.unit_price || Number.isNaN(priceNum) || priceNum <= 0) {
            setError('Please enter a valid unit price (must be greater than 0).');
            return;
        }

        const payload = {
            name: form.name.trim(),
            category_id: categoryId,
            unit_price: priceNum,
            unit_label: form.unit_label.trim() || 'piece',
            is_available_today: form.is_available_today,
            aliases: parseAliases(form.aliases_text),
        };
        if (form.description.trim()) payload.description = form.description.trim();

        // Step 3: create or update the product.
        try {
            if (mode === 'edit') {
                await updateProductMut.mutateAsync({ id: product.id, payload });
            } else {
                await createProductMut.mutateAsync(payload);
            }
            onClose();
        } catch (err) {
            const detail = err.response?.data?.detail;
            setError(typeof detail === 'string' ? detail : 'Could not save product. Please check the form and try again.');
        }
    }

    // === Filtered category dropdown options ===
    // Show categories whose name CONTAINS the typed text (case-insensitive).
    // If exact match: dropdown shows just that match. If no match: dropdown
    // shows an "Add new: X" option.
    const allCategories = categoriesQuery.data?.items ?? [];
    const typed = form.category_typed.trim().toLowerCase();
    const filteredCategories = typed
        ? allCategories.filter((c) => c.name.includes(typed))
        : allCategories;
    const hasExactMatch = allCategories.some((c) => c.name === typed);
    const showCreateOption = typed && !hasExactMatch;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 p-4"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="product-modal-title"
        >
            <form
                onSubmit={handleSubmit}
                onClick={(e) => e.stopPropagation()}
                className="bg-white border border-slate-200 rounded-lg shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto"
            >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <h2 id="product-modal-title" className="text-base font-medium text-slate-900">
                        {mode === 'edit' ? 'Edit product' : 'Add new product'}
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

                {/* === Section 1: Basics === */}
                <div className="space-y-3 mb-5">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Basics
                    </p>

                    {/* Name (required) */}
                    <div>
                        <label htmlFor="pf-name" className="block text-sm text-slate-700 mb-1">
                            Product name <span className="text-red-600">*</span>
                        </label>
                        <input
                            id="pf-name"
                            type="text"
                            required
                            value={form.name}
                            onChange={(e) => handleChange('name', e.target.value)}
                            placeholder="Veg Puff"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                    </div>

                    {/* Category combobox (required) */}
                    <div ref={comboboxRef}>
                        <label htmlFor="pf-category" className="block text-sm text-slate-700 mb-1">
                            Category <span className="text-red-600">*</span>
                        </label>
                        <div className="relative">
                            <input
                                id="pf-category"
                                type="text"
                                required
                                value={form.category_typed}
                                onChange={(e) => {
                                    handleCategoryTyped(e.target.value);
                                    setCategoryDropdownOpen(true);
                                }}
                                onFocus={() => setCategoryDropdownOpen(true)}
                                placeholder="savoury, sweet, cake..."
                                autoComplete="off"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />

                            {/* Dropdown panel */}
                            {categoryDropdownOpen && (filteredCategories.length > 0 || showCreateOption) && (
                                <ul className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                                    {filteredCategories.map((c) => (
                                        <li key={c.id}>
                                            <button
                                                type="button"
                                                onClick={() => pickExistingCategory(c)}
                                                className="w-full text-left px-3 py-2 text-sm hover:bg-brand-50 hover:text-brand-700"
                                            >
                                                {c.name}
                                            </button>
                                        </li>
                                    ))}
                                    {showCreateOption && (
                                        <li className="border-t border-slate-200">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    // Just close the dropdown; the submit handler
                                                    // will create the category on save.
                                                    setCategoryDropdownOpen(false);
                                                }}
                                                className="w-full text-left px-3 py-2 text-sm text-green-700 hover:bg-green-50"
                                            >
                                                + Create new category: <strong>"{typed}"</strong>
                                            </button>
                                        </li>
                                    )}
                                </ul>
                            )}
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                            Pick existing or type a new category name
                        </p>
                    </div>

                    {/* Price + Unit label row */}
                    <div className="grid grid-cols-3 gap-3">
                        <div className="col-span-2">
                            <label htmlFor="pf-price" className="block text-sm text-slate-700 mb-1">
                                Unit price (₹) <span className="text-red-600">*</span>
                            </label>
                            <input
                                id="pf-price"
                                type="number"
                                step="0.01"
                                min="0.01"
                                required
                                value={form.unit_price}
                                onChange={(e) => handleChange('unit_price', e.target.value)}
                                placeholder="20.00"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 font-mono"
                            />
                        </div>
                        <div>
                            <label htmlFor="pf-unit-label" className="block text-sm text-slate-700 mb-1">
                                Per
                            </label>
                            <input
                                id="pf-unit-label"
                                type="text"
                                value={form.unit_label}
                                onChange={(e) => handleChange('unit_label', e.target.value)}
                                placeholder="piece"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                            />
                        </div>
                    </div>
                </div>

                {/* === Section 2: Availability & aliases === */}
                <div className="space-y-3 mb-5 pt-4 border-t border-slate-200">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Availability & bot aliases
                    </p>

                    {/* Available today toggle */}
                    <label className="flex items-center gap-2 py-1 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={form.is_available_today}
                            onChange={(e) => handleChange('is_available_today', e.target.checked)}
                            className="rounded border-slate-300"
                        />
                        <span className="text-sm text-slate-700">Available today</span>
                        <span className="text-xs text-slate-500">— shows in the bot menu</span>
                    </label>

                    {/* Aliases (comma-separated) */}
                    <div>
                        <label htmlFor="pf-aliases" className="block text-sm text-slate-700 mb-1">
                            Bot aliases
                        </label>
                        <input
                            id="pf-aliases"
                            type="text"
                            value={form.aliases_text}
                            onChange={(e) => handleChange('aliases_text', e.target.value)}
                            placeholder="puff, veg puff, vegetable puff"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
                        />
                        <p className="text-xs text-slate-500 mt-1">
                            Words customers might use, separated by commas
                        </p>
                    </div>
                </div>

                {/* === Section 3: Description === */}
                <div className="space-y-3 mb-5 pt-4 border-t border-slate-200">
                    <p className="text-xs uppercase tracking-wide text-slate-500 font-medium">
                        Description <span className="lowercase text-slate-400 font-normal">(optional)</span>
                    </p>
                    <textarea
                        rows={2}
                        value={form.description}
                        onChange={(e) => handleChange('description', e.target.value)}
                        placeholder="Crispy savoury pastry with vegetable filling"
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
                        {isSubmitting ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Add product'}
                    </button>
                </div>
            </form>
        </div>
    );
}