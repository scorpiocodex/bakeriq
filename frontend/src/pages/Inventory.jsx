/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */
/**
 * Inventory — stock for sealed goods, prep list for everything else.
 *
 * The bakery sells two kinds of thing. Sealed goods (ladoo packets,
 * bread, biscuits) carry over between days and have a countable quantity.
 * Puffs and the like are baked and sold the same day, so they have no
 * stock — what the chef needs for those is a prep list, derived from
 * today's orders.
 *
 * Counts are edited inline rather than through a modal. The owner's
 * actual workflow is "count the shelf, type the number, move on", and a
 * dialog per product would make that worse.
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, Boxes, ChefHat, Plus, X } from 'lucide-react';

import RowActionsMenu from '../components/RowActionsMenu';
import {
  usePrepList,
  useSetStock,
  useStockList,
  useUpdateStockSettings,
} from '../hooks/useInventory';
import { useProductsList } from '../hooks/useProducts';

// =============================================================================
// Inline count editor
// =============================================================================

/**
 * A number input that commits on blur or Enter and reverts on Escape.
 *
 * Deliberately not debounced-autosave: a half-typed "1" on the way to
 * "15" would briefly write 1, and with stock that's a number the owner
 * might act on.
 */
function StockCell({ product, onSave, isSaving }) {
  const [value, setValue] = useState(String(product.stock_quantity ?? 0));
  const [dirty, setDirty] = useState(false);

  // Resync when the server value changes underneath us — an order coming
  // in while the page is open, or another edit landing.
  useEffect(() => {
    if (!dirty) setValue(String(product.stock_quantity ?? 0));
  }, [product.stock_quantity, dirty]);

  function commit() {
    setDirty(false);
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < 0) {
      setValue(String(product.stock_quantity ?? 0));
      return;
    }
    if (parsed === product.stock_quantity) return;
    onSave(parsed);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      e.target.blur();
    } else if (e.key === 'Escape') {
      setDirty(false);
      setValue(String(product.stock_quantity ?? 0));
      e.target.blur();
    }
  }

  return (
    <input
      type="number"
      min={0}
      value={value}
      disabled={isSaving}
      onChange={(e) => {
        setDirty(true);
        setValue(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={handleKeyDown}
      className={`w-20 text-xs px-2 py-1 border rounded-md text-right focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500 disabled:opacity-50 ${
        product.is_low_stock ? 'border-amber-300 bg-amber-50' : 'border-slate-300'
      }`}
      aria-label={`Stock for ${product.name}`}
    />
  );
}

// =============================================================================
// Threshold editor — lives in a small popover off the row menu
// =============================================================================

function ThresholdModal({ open, product, isProcessing, onConfirm, onCancel }) {
  const [value, setValue] = useState('');

  useEffect(() => {
    if (open && product) {
      setValue(product.low_stock_threshold === null ? '' : String(product.low_stock_threshold));
    }
  }, [open, product]);

  if (!open || !product) return null;

  function handleConfirm() {
    const parsed = value.trim() === '' ? null : parseInt(value, 10);
    if (parsed !== null && (Number.isNaN(parsed) || parsed < 0)) return;
    onConfirm(parsed);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onCancel} aria-hidden="true" />
      <div className="relative bg-white rounded-lg shadow-lg border border-slate-200 w-full max-w-xs p-4">
        <p className="text-sm font-medium text-slate-900">Low-stock warning</p>
        <p className="text-xs text-slate-600 mt-1.5">
          Warn when {product.name} falls to this level or below.
        </p>

        <label htmlFor="threshold" className="block text-xs font-medium text-slate-700 mt-3 mb-1">
          Threshold <span className="text-slate-400">(blank for no warning)</span>
        </label>
        <input
          id="threshold"
          type="number"
          min={0}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="e.g. 5"
          className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
        />

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            disabled={isProcessing}
            className="text-xs px-3 py-1.5 border border-slate-300 text-slate-700 rounded-md hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isProcessing}
            className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium disabled:opacity-50"
          >
            {isProcessing ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Start-tracking picker
// =============================================================================

/**
 * Every product starts untracked, so without this the page would be
 * permanently empty and there'd be no way in from the UI.
 */
function TrackProductModal({ open, products, isProcessing, onConfirm, onCancel }) {
  const [selected, setSelected] = useState('');

  useEffect(() => {
    if (open) setSelected('');
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onCancel} aria-hidden="true" />
      <div className="relative bg-white rounded-lg shadow-lg border border-slate-200 w-full max-w-sm p-4">
        <p className="text-sm font-medium text-slate-900">Track stock for a product</p>
        <p className="text-xs text-slate-600 mt-1.5">
          Only for items you pack and seal — things that keep between days. Freshly baked items
          don&apos;t hold stock; they show up in the prep list instead.
        </p>

        {products.length === 0 ? (
          <p className="text-xs text-slate-500 mt-3 py-4 text-center">
            Every product is already tracked.
          </p>
        ) : (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded-md mt-3 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-500"
          >
            <option value="">Pick a product…</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            disabled={isProcessing}
            className="text-xs px-3 py-1.5 border border-slate-300 text-slate-700 rounded-md hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(selected)}
            disabled={!selected || isProcessing}
            className="text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium disabled:opacity-50"
          >
            {isProcessing ? 'Adding…' : 'Start tracking'}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// The page
// =============================================================================

export default function Inventory() {
  const [thresholdTarget, setThresholdTarget] = useState(null);
  const [trackOpen, setTrackOpen] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [actionError, setActionError] = useState(null);

  const stockQuery = useStockList();
  const prepQuery = usePrepList();
  const productsQuery = useProductsList({ status: 'active' });

  const setStockMut = useSetStock();
  const settingsMut = useUpdateStockSettings();

  const stock = stockQuery.data?.items ?? [];
  const lowCount = stockQuery.data?.low_stock_count ?? 0;
  const prep = prepQuery.data;

  // Only untracked products can be added — the rest are already listed.
  const trackable = (productsQuery.data?.items ?? []).filter(
    (p) => !stock.some((s) => s.id === p.id),
  );

  async function handleSetStock(product, quantity) {
    setActionError(null);
    setSavingId(product.id);
    try {
      await setStockMut.mutateAsync({ id: product.id, quantity });
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? `Could not update ${product.name}.`);
    } finally {
      setSavingId(null);
    }
  }

  async function handleThreshold(threshold) {
    if (!thresholdTarget) return;
    setActionError(null);
    try {
      await settingsMut.mutateAsync({
        id: thresholdTarget.id,
        payload: { low_stock_threshold: threshold },
      });
      setThresholdTarget(null);
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? 'Could not save the threshold.');
      setThresholdTarget(null);
    }
  }

  async function handleStopTracking(product) {
    setActionError(null);
    try {
      await settingsMut.mutateAsync({
        id: product.id,
        payload: { is_stockable: false },
      });
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? `Could not stop tracking ${product.name}.`);
    }
  }

  async function handleStartTracking(productId) {
    setActionError(null);
    try {
      await settingsMut.mutateAsync({
        id: productId,
        payload: { is_stockable: true },
      });
      setTrackOpen(false);
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? 'Could not start tracking.');
      setTrackOpen(false);
    }
  }

  return (
    <>
      {/* === Header === */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-slate-900">Inventory</p>
          <p className="text-xs text-slate-500">
            {stockQuery.isLoading
              ? 'Loading…'
              : lowCount > 0
                ? `${stock.length} tracked · ${lowCount} running low`
                : `${stock.length} tracked`}
          </p>
        </div>
        <button
          onClick={() => setTrackOpen(true)}
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-md font-medium"
        >
          <Plus size={14} />
          Track a product
        </button>
      </div>

      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-2.5">
          <p className="text-xs text-red-700">{actionError}</p>
        </div>
      )}

      {/* === Low stock banner === */}
      {lowCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2.5 flex items-center gap-2">
          <AlertTriangle size={14} className="text-amber-600 shrink-0" />
          <p className="text-xs text-amber-800">
            {lowCount} {lowCount === 1 ? 'product is' : 'products are'} at or below the warning
            level.
          </p>
        </div>
      )}

      {/* === Stock table === */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto mb-3">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-left">
              <th className="px-3 py-2 font-medium">Product</th>
              <th className="px-3 py-2 font-medium">Unit</th>
              <th className="px-3 py-2 font-medium text-right">In stock</th>
              <th className="px-3 py-2 font-medium text-right">Warn at</th>
              <th className="px-3 py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="text-slate-900">
            {stockQuery.isLoading && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-500">
                  Loading stock…
                </td>
              </tr>
            )}

            {stockQuery.isError && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-red-700">
                  Could not load stock levels.
                </td>
              </tr>
            )}

            {!stockQuery.isLoading && !stockQuery.isError && stock.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-10 text-center">
                  <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center mx-auto mb-2">
                    <Boxes size={18} className="text-slate-400" />
                  </div>
                  <p className="text-xs text-slate-600">Nothing tracked yet.</p>
                  <p className="text-[11px] text-slate-500 mt-1 max-w-xs mx-auto">
                    Track the items you pack and seal — ladoo packets, bread, biscuits. Freshly
                    baked items appear in the prep list instead.
                  </p>
                </td>
              </tr>
            )}

            {stock.map((p) => (
              <tr
                key={p.id}
                className={`border-b border-slate-100 last:border-b-0 ${
                  p.is_low_stock ? 'bg-amber-50/40' : ''
                }`}
              >
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    {p.is_low_stock && (
                      <AlertTriangle
                        size={13}
                        className="text-amber-600 shrink-0"
                        aria-label="Low stock"
                      />
                    )}
                    <span className="font-medium">{p.name}</span>
                  </div>
                </td>
                <td className="px-3 py-2.5 text-slate-600">{p.unit_label}</td>
                <td className="px-3 py-2.5 text-right">
                  <StockCell
                    product={p}
                    isSaving={savingId === p.id}
                    onSave={(q) => handleSetStock(p, q)}
                  />
                </td>
                <td className="px-3 py-2.5 text-right text-slate-600">
                  {p.low_stock_threshold ?? <span className="text-slate-400">—</span>}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <RowActionsMenu
                    actions={[
                      {
                        label: 'Set warning level',
                        onClick: () => setThresholdTarget(p),
                      },
                      {
                        label: 'Stop tracking',
                        destructive: true,
                        disabled: settingsMut.isPending,
                        onClick: () => handleStopTracking(p),
                      },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* === Prep list ===
          Only while the window is open. Before the 5 AM order cutoff the
          numbers are still moving; after the day's baking they're history. */}
      {prep?.is_visible && (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
            <ChefHat size={14} className="text-slate-500" />
            <p className="text-xs font-medium text-slate-700">To make today</p>
            <span className="text-[10px] text-slate-500 ml-auto">from today&apos;s orders</span>
          </div>

          {prep.items.length === 0 ? (
            <p className="px-3 py-6 text-xs text-center text-slate-500">
              Nothing ordered for today yet.
            </p>
          ) : (
            <table className="w-full text-xs">
              <tbody className="text-slate-900">
                {prep.items.map((item) => (
                  <tr key={item.product_id} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-3 py-2 font-medium">{item.product_name}</td>
                    <td className="px-3 py-2 text-slate-500 text-[11px]">
                      across {item.order_count} {item.order_count === 1 ? 'order' : 'orders'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="font-semibold text-brand-700">{item.quantity}</span>{' '}
                      <span className="text-slate-500">{item.unit_label}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* === Modals === */}
      <ThresholdModal
        open={thresholdTarget !== null}
        product={thresholdTarget}
        isProcessing={settingsMut.isPending}
        onConfirm={handleThreshold}
        onCancel={() => setThresholdTarget(null)}
      />

      <TrackProductModal
        open={trackOpen}
        products={trackable}
        isProcessing={settingsMut.isPending}
        onConfirm={handleStartTracking}
        onCancel={() => setTrackOpen(false)}
      />
    </>
  );
}
