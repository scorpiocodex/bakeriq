import { Boxes } from 'lucide-react';

export default function Inventory() {
  return (
    <>
      <div className="mb-3">
        <p className="text-sm font-medium text-slate-900">Inventory</p>
        <p className="text-xs text-slate-500">Stock levels, ingredient pool, low-stock alerts</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-10 flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center mb-3">
          <Boxes size={22} className="text-slate-400" />
        </div>
        <p className="text-sm font-medium text-slate-700">Inventory tracking coming soon</p>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Stock pools, ingredient deduction per order, and low-stock alerts arrive in Phase 5.
        </p>
        <span className="mt-3 text-[10px] uppercase tracking-wider text-slate-400 font-medium">
          Phase 5
        </span>
      </div>
    </>
  );
}
