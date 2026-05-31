import { Receipt } from 'lucide-react';

export default function Billing() {
  return (
    <>
      <div className="mb-3">
        <p className="text-sm font-medium text-slate-900">Billing</p>
        <p className="text-xs text-slate-500">Receipts, invoices, and payment tracking</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-10 flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center mb-3">
          <Receipt size={22} className="text-slate-400" />
        </div>
        <p className="text-sm font-medium text-slate-700">Billing & receipts coming soon</p>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Receipt generation, daily/monthly invoice rollups, and payment tracking arrive in Phase 6.
        </p>
        <span className="mt-3 text-[10px] uppercase tracking-wider text-slate-400 font-medium">
          Phase 6
        </span>
      </div>
    </>
  );
}
