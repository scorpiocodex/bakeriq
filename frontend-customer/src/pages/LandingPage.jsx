export default function LandingPage() {
  return (
    <div className="app-container">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
      </header>

      <div className="bg-white rounded-lg shadow-sm border border-brand-100 p-6 text-center">
        <p className="text-gray-700 mb-2">Welcome!</p>
        <p className="text-sm text-gray-600">
          This page is reached via WhatsApp ordering links. To place an order, message us on
          WhatsApp.
        </p>
      </div>
    </div>
  );
}
