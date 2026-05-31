const VARIANTS = {
  active: { bg: 'bg-green-100', text: 'text-green-800', label: 'Active' },
  inactive: { bg: 'bg-slate-200', text: 'text-slate-600', label: 'Inactive' },
  received: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Received' },
  preparing: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Preparing' },
  ready: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Ready' },
  delivering: { bg: 'bg-teal-100', text: 'text-teal-800', label: 'Delivering' },
  cancelled: { bg: 'bg-red-100', text: 'text-red-700', label: 'Cancelled' },
};

export default function StatusBadge({ status, label, size = 'sm' }) {
  const v = VARIANTS[status?.toLowerCase()] ?? VARIANTS.inactive;
  const sizing = size === 'xs' ? 'text-[10px] px-2 py-0.5' : 'text-xs px-2.5 py-0.5';

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${sizing} ${v.bg} ${v.text}`}
    >
      {label ?? v.label}
    </span>
  );
}
