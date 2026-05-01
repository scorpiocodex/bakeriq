import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

/**
 * Layout shell wrapping every authenticated route.
 *
 * Layout is a *layout route* in App.jsx — it renders <Outlet /> where the
 * matched child route (Dashboard, Orders, etc.) goes. This pattern means
 * the sidebar and topbar mount ONCE and stay mounted as the user
 * navigates; only the main content swaps. Faster than re-rendering the
 * shell every navigation.
 */
export default function Layout() {
    return (
        <div className="min-h-screen bg-slate-100 p-3">
            <div className="grid grid-cols-[14rem_1fr] gap-3 max-w-[1400px] mx-auto">
                <Sidebar />
                <main>
                    <TopBar />
                    <Outlet />
                </main>
            </div>
        </div>
    );
}