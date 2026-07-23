import { useState } from 'react';
import { Plus } from 'lucide-react';
import { formatRupees } from '../lib/format';

/**
 * Expandable "Add an item" picker. Shows the menu grouped by category.
 * Tapping an item adds it to the cart with quantity 1.
 *
 * Collapsed by default so the cart page doesn't feel overwhelming
 * when reorder mode has a pre-filled cart already.
 */
export default function MenuPicker({ menu, cartItemIds, onAdd }) {
  const [expanded, setExpanded] = useState(false);

  // Group menu by category — same pattern as the bot's text menu.
  const byCategory = menu.reduce((acc, product) => {
    const cat = product.category_name || 'Other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(product);
    return acc;
  }, {});

  // Filter out items already in the cart
  const available = (products) => products.filter((p) => !cartItemIds.has(p.id));

  return (
    <div className="bg-white rounded-lg shadow-sm border border-brand-100 mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3
                   text-left font-semibold text-brand-700
                   hover:bg-brand-50 active:bg-brand-100
                   rounded-lg transition-colors"
      >
        <span>{expanded ? 'Hide menu' : 'Add more items'}</span>
        <Plus size={20} className={`transition-transform ${expanded ? 'rotate-45' : ''}`} />
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {Object.keys(byCategory)
            .sort()
            .map((category) => {
              const items = available(byCategory[category]);
              if (items.length === 0) return null;
              return (
                <div key={category} className="mt-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
                    {category}
                  </h3>
                  {items.map((product) => (
                    <button
                      key={product.id}
                      onClick={() => onAdd(product)}
                      className="w-full flex items-center justify-between gap-3 py-2 px-2
                               hover:bg-brand-50 rounded transition-colors text-left"
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900">{product.name}</p>
                        <p className="text-xs text-gray-500">
                          {formatRupees(product.unit_price)} / {product.unit_label}
                          {product.is_low_stock && (
                            <span className="ml-2 text-amber-600 font-medium">Low stock</span>
                          )}
                        </p>
                      </div>
                      <Plus size={18} className="text-brand-600 flex-shrink-0" />
                    </button>
                  ))}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
