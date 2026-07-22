import { formatRupees } from '../lib/format';
import QuantityStepper from './QuantityStepper';

/**
 * Single cart item row.
 *
 * Shows product name + unit, the line subtotal, and the quantity
 * stepper. Quantity changes call onQuantityChange — parent owns the
 * state. Setting quantity to 0 leaves the row visible so the customer
 * can re-add — they remove with the X button if they truly don't want it.
 */
export default function CartItemRow({ item, onQuantityChange, onRemove }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3 border-b border-gray-100 last:border-b-0">
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 truncate">{item.product_name}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {formatRupees(item.unit_price)} / {item.unit_label}
        </p>
        <p className="text-sm font-semibold text-brand-700 mt-1">{formatRupees(item.subtotal)}</p>
      </div>

      <QuantityStepper value={item.quantity} onChange={onQuantityChange} />
    </div>
  );
}
