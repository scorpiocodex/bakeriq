import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Approvals from './pages/Approvals';
import Billing from './pages/Billing';
import Customers from './pages/Customers';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Login from './pages/Login';
import Orders from './pages/Orders';
import Products from './pages/Products';
import BillingCustomer from './pages/BillingCustomer';
import BillingInvoice from './pages/BillingInvoice';
import Settings from './pages/Settings';

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />

      {/* Protected routes — wrapped in Layout (sidebar + topbar) */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/products" element={<Products />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/billing" element={<Billing />} />
        <Route path="/billing/:customerId" element={<BillingCustomer />} />
        <Route path="/billing/:customerId/invoice/:invoiceDate" element={<BillingInvoice />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      {/* Catch-all: redirect unknown paths to the dashboard. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
