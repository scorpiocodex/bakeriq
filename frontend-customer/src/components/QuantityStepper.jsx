import { Minus, Plus } from 'lucide-react';

/**
 * Quantity stepper with +/- buttons and a numeric display.
 *
 * Designed for thumb-comfortable touch targets on mobile (each button
 * is at least 44x44 — same heuristic Apple uses for the iOS HIG).
 * Quantities clamp at 0 minimum; max is enforced by the parent.
 */
export default function QuantityStepper({ value, onChange, min = 0, max = 999 }) {
  const decrement = () => {
    if (value > min) onChange(value - 1);
  };

  const increment = () => {
    if (value < max) onChange(value + 1);
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={decrement}
        disabled={value <= min}
        className="w-10 h-10 flex items-center justify-center
                   bg-brand-50 hover:bg-brand-100 active:bg-brand-200
                   disabled:opacity-40 disabled:cursor-not-allowed
                   text-brand-700 rounded-md transition-colors"
        aria-label="Decrease quantity"
      >
        <Minus size={18} strokeWidth={2.5} />
      </button>

      <span className="w-8 text-center font-semibold text-gray-900">{value}</span>

      <button
        onClick={increment}
        disabled={value >= max}
        className="w-10 h-10 flex items-center justify-center
                   bg-brand-600 hover:bg-brand-700 active:bg-brand-800
                   disabled:opacity-40 disabled:cursor-not-allowed
                   text-white rounded-md transition-colors"
        aria-label="Increase quantity"
      >
        <Plus size={18} strokeWidth={2.5} />
      </button>
    </div>
  );
}
