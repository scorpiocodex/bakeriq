/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */

/**
 * Sidebar
 **/
import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Boxes,
  ClipboardCheck,
  LayoutDashboard,
  LogOut,
  ShoppingBag,
  Receipt,
  Settings,
  ShoppingCart,
  Users,
} from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { useApprovalsCount } from '../hooks/useApprovals';
import BrandMark from './BrandMark';

// `badge: 'approvals'` marks an item as carrying a live count. The render
// loop looks the number up rather than storing it here, so NAV_SECTIONS
// stays a static description of the nav rather than a stateful thing.
const NAV_SECTIONS = [
  {
    label: 'Operations',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
      { to: '/orders', label: 'Orders', icon: ShoppingCart },
      { to: '/approvals', label: 'Approvals', icon: ClipboardCheck, badge: 'approvals' },
      { to: '/customers', label: 'Customers', icon: Users },
      { to: '/products', label: 'Products', icon: ShoppingBag },
    ],
  },
  {
    label: 'Setup',
    items: [
      { to: '/inventory', label: 'Inventory', icon: Boxes },
      { to: '/billing', label: 'Billing', icon: Receipt },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export default function Sidebar({ mobileOpen, onClose }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  // Polls every 30s (see useApprovals). Failure is silent on purpose — a
  // flaky count request shouldn't put an error state in the nav; the
  // badge just doesn't render until a poll succeeds.
  const { data: approvalsCount } = useApprovalsCount();
  const pendingApprovals = approvalsCount?.count ?? 0;

  useEffect(() => {
    if (mobileOpen) onClose();
  }, [location.pathname]);

  // Close on Escape (good keyboard hygiene for the mobile overlay)
  useEffect(() => {
    if (!mobileOpen) return;
    function onKey(e) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mobileOpen, onClose]);

  return (
    <>
      {/* Mobile backdrop — only on small screens AND when open */}
      <div
        className={`fixed inset-0 z-30 bg-slate-900/30 lg:hidden transition-opacity ${
          mobileOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* The sidebar itself.
          - Desktop (lg+): static column, always visible
          - Mobile: fixed-position drawer that slides in/out via translate-x */}
      <aside
        className={`
          fixed lg:static top-0 left-0 z-40 h-full w-64 flex-shrink-0
          bg-white border-r border-slate-200 flex flex-col
          transform transition-transform duration-200 ease-out
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          lg:translate-x-0
        `}
        aria-label="Primary navigation"
      >
        {/* Brand header */}
        <div className="flex items-center gap-2 px-4 py-4 border-b border-slate-100">
          <BrandMark size="sm" />
          <div>
            <p className="text-sm font-medium text-slate-900 leading-tight">BakeriQ</p>
            <p className="text-[10px] text-slate-500 leading-tight">Bakery operations</p>
          </div>
        </div>

        {/* Nav (grouped) */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <p className="px-2 mb-1 text-[10px] uppercase tracking-wider text-slate-500 font-medium">
                {section.label}
              </p>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const badgeCount = item.badge === 'approvals' ? pendingApprovals : 0;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.exact}
                        className={({ isActive }) =>
                          `relative flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                            isActive
                              ? 'bg-brand-50 text-brand-700 font-medium'
                              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                          }`
                        }
                      >
                        {({ isActive }) => (
                          <>
                            {/* Left accent bar for the active state */}
                            {isActive && (
                              <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r bg-brand-600" />
                            )}
                            <Icon
                              size={16}
                              className={isActive ? 'text-brand-600' : 'text-slate-500'}
                              aria-hidden="true"
                            />
                            <span>{item.label}</span>
                            {/* Count badge — hidden at zero so a cleared
                                queue doesn't leave a "0" sitting there */}
                            {badgeCount > 0 && (
                              <span
                                className="ml-auto min-w-[18px] h-[18px] px-1 flex items-center justify-center text-[10px] font-semibold rounded-full bg-amber-500 text-white"
                                aria-label={`${badgeCount} awaiting approval`}
                              >
                                {badgeCount > 99 ? '99+' : badgeCount}
                              </span>
                            )}
                          </>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Footer — avatar + identity + logout */}
        <div className="border-t border-slate-100 p-3">
          <div className="flex items-center gap-2.5">
            <div
              className="w-9 h-9 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-xs font-semibold flex-shrink-0"
              aria-hidden="true"
            >
              {user?.full_name?.[0]?.toUpperCase() ?? 'B'}
              {user?.full_name?.split(' ')[1]?.[0]?.toUpperCase() ?? 'O'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900 truncate">
                {user?.full_name ?? 'Owner'}
              </p>
              <p className="text-[11px] text-slate-500 truncate">{user?.email ?? ''}</p>
            </div>
            <button
              onClick={logout}
              title="Log out"
              aria-label="Log out"
              className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
