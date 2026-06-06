import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ReorderPage from './pages/ReorderPage';
import NewOrderPage from './pages/NewOrderPage';
import EditPage from './pages/EditPage';
import LandingPage from './pages/LandingPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Token-scoped customer pages — accessed only via WhatsApp links */}
        <Route path="/reorder/:token" element={<ReorderPage />} />
        <Route path="/new/:token" element={<NewOrderPage />} />
        <Route path="/edit/:token" element={<EditPage />} />

        {/* Anyone who hits the bare domain (e.g. typed in by mistake)
            gets a friendly landing page rather than a router 404. */}
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<LandingPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
