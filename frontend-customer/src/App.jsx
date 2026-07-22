// PATCH to frontend-customer/src/App.jsx
//
// Add the import at the top with the other page imports:
//
//   import RegistrationPage from './pages/RegistrationPage';
//
// Add the route inside <Routes>, before the LandingPage catch-all:
//
//   <Route path="/register/:token" element={<RegistrationPage />} />
//
// Final App.jsx looks like this:

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ReorderPage from './pages/ReorderPage';
import NewOrderPage from './pages/NewOrderPage';
import EditPage from './pages/EditPage';
import RegistrationPage from './pages/RegistrationPage';
import LandingPage from './pages/LandingPage';

// The basename is set so React Router works both when accessed directly
// (basename='') for dev at localhost:5174 and when accessed via the
// FastAPI /web/ proxy (basename='/web') in the WhatsApp link flow.
//
// Detect at runtime from window.location — simpler than threading an env
// var through the build, and we want both URL forms to work in dev.
const basename =
  typeof window !== 'undefined' && window.location.pathname.startsWith('/web') ? '/web' : '';

function App() {
  return (
    <BrowserRouter basename={basename}>
      <Routes>
        <Route path="/reorder/:token" element={<ReorderPage />} />
        <Route path="/new/:token" element={<NewOrderPage />} />
        <Route path="/edit/:token" element={<EditPage />} />
        <Route path="/register/:token" element={<RegistrationPage />} />
        <Route path="/" element={<LandingPage />} />
        <Route path="*" element={<LandingPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
