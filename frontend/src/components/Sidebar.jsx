import { NavLink } from 'react-router-dom';

// Centralised nav definition — used by both desktop sidebar and (later)
// mobile bottom-bar. Adding a new section is one entry, not three.
const navItems = [
    { to: '/', label: 'Dashboard', end: true },
    { to: '/orders', label: 'Orders' },
    { to: '/customers', label: 'Customers' },
    { to: '/products', label: 'Products' },
    { to: '/inventory', label: 'Inventory' },
    { to: '/analytics', label: 'Analytics' },
    { to: '/billing', label: 'Billing' },
    { to: '/settings', label: 'Settings' },
];

export default function Sidebar() {
    return (
        <aside className="w-56 bg-white border border-slate-200 rounded-xl p-3 flex-shrink-0">
            {/* Brand mark — same as login page so the visual transition is seamless */}
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-200">
                <div className="w-7 h-7 rounded-md bg-brand-600 text-white text-sm font-medium flex items-center justify-center">
                    B
                </div>
                <span className="text-sm font-medium text-slate-900">BakeriQ</span>
            </div>

            {/* Nav list */}
            <nav className="flex flex-col gap-0.5">
                {navItems.map((item) => (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        className={({ isActive }) =>
                            [
                                'px-2.5 py-1.5 rounded-md text-sm transition-colors',
                                isActive
                                    ? 'bg-brand-50 text-brand-700 font-medium'
                                    : 'text-slate-600 hover:bg-slate-50',
                            ].join(' ')
                        }
                    >
                        {item.label}
                    </NavLink>
                ))}
            </nav>
        </aside>
    );
}