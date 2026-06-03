/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */
import {
  CheckCircle2,
  ChefHat,
  CircleDot,
  CircleSlash,
  Clock,
  PackageCheck,
  Truck,
  XCircle,
} from 'lucide-react';

/**
 * Shared status pill — colour + icon + label.
 *
 * Used across Orders, Customers, Products, Settings/Categories, and
 * OrderDetailPanel. The icon is part of the design, not decoration:
 * never communicate status by colour alone (WCAG, colour-blind users).
 *
 * Variants map to status strings the API returns lowercased.
 */
const VARIANTS = {
  // Customer/product/category active state
  active: { bg: 'bg-green-100', text: 'text-green-800', label: 'Active', Icon: CheckCircle2 },
  inactive: { bg: 'bg-slate-200', text: 'text-slate-700', label: 'Inactive', Icon: CircleSlash },

  // Order lifecycle
  received: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Received', Icon: CircleDot },
  preparing: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Preparing', Icon: ChefHat },
  ready: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Ready', Icon: PackageCheck },
  delivering: { bg: 'bg-teal-100', text: 'text-teal-800', label: 'Delivering', Icon: Truck },
  cancelled: { bg: 'bg-red-100', text: 'text-red-700', label: 'Cancelled', Icon: XCircle },

  // Generic fallback used if a new status appears we haven't styled yet
  unknown: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Unknown', Icon: Clock },
};

export default function StatusBadge({ status, label, size = 'sm' }) {
  const v = VARIANTS[status?.toLowerCase()] ?? VARIANTS.unknown;
  const Icon = v.Icon;

  const sizing =
    size === 'xs'
      ? { pill: 'text-[10px] px-2 py-0.5 gap-1', icon: 10 }
      : { pill: 'text-xs px-2.5 py-0.5 gap-1', icon: 12 };

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${sizing.pill} ${v.bg} ${v.text}`}
    >
      <Icon size={sizing.icon} aria-hidden="true" strokeWidth={2.5} />
      <span>{label ?? v.label}</span>
    </span>
  );
}
