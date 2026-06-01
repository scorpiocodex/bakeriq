import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="h-screen bg-slate-100 p-3 overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-[16rem_1fr] gap-3 max-w-[1400px] mx-auto h-full">
        <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <main className="min-w-0 overflow-y-auto">
          <TopBar onMenuClick={() => setMobileOpen(true)} />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
