import { useParams } from 'react-router-dom';
import { useCart } from '../hooks/useCart';
import CartItemRow from '../components/CartItemRow';
import MenuPicker from '../components/MenuPicker';
import { formatRupees } from '../lib/format';

export default function NewOrderPage() {
  const { token } = useParams();
  const {
    status,
    cart,
    items,
    total,
    error,
    updateQuantity,
    addItem,
    save,
    place,
    saveStatus,
    placeStatus,
    placedOrder,
  } = useCart(token);

  if (status === 'loading') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <p className="text-gray-600">Loading today's menu…</p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-red-200 p-4">
          <p className="font-semibold text-red-700">Link no longer valid</p>
          <p className="text-sm text-gray-700 mt-2">
            {error?.response?.data?.detail ||
              'This link has expired or already been used. Please request a new link from the bot.'}
          </p>
        </div>
      </div>
    );
  }

  if (status === 'placed') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-brand-200 p-6 text-center">
          <p className="text-2xl mb-2">✓</p>
          <p className="font-semibold text-gray-900">Order placed!</p>
          <p className="text-sm text-gray-600 mt-2">
            Order #{placedOrder?.order_id?.slice(0, 8)} — {formatRupees(placedOrder?.total)}
          </p>
          <p className="text-sm text-gray-600 mt-3">
            You can close this page and return to WhatsApp. We'll send updates as your order
            progresses.
          </p>
        </div>
      </div>
    );
  }

  const cartItemIds = new Set(items.filter((i) => i.quantity > 0).map((i) => i.product_id));
  const hasItems = items.some((i) => i.quantity > 0);
  const customerName = cart.customer.name.split(' ')[0];

  return (
    <div className="app-container pb-32">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        <p className="mt-1 text-sm text-gray-600">
          Hi {customerName} — pick what you'd like to order today.
        </p>
      </header>

      <div className="bg-white rounded-lg shadow-sm border border-brand-100 p-4">
        {items.length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-4">
            Your cart is empty. Add items from the menu below.
          </p>
        ) : (
          items.map((item) => (
            <CartItemRow
              key={item.product_id}
              item={item}
              onQuantityChange={(q) => updateQuantity(item.product_id, q)}
            />
          ))
        )}
      </div>

      <MenuPicker menu={cart.menu} cartItemIds={cartItemIds} onAdd={addItem} />

      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-brand-100 shadow-lg">
        <div className="mx-auto max-w-app px-4 py-4">
          <div className="flex justify-between items-baseline mb-3">
            <span className="text-sm text-gray-600">Total</span>
            <span className="text-xl font-bold text-brand-700">{formatRupees(total)}</span>
          </div>
          <button
            className="btn-primary disabled:opacity-50"
            disabled={!hasItems || placeStatus === 'pending'}
            onClick={() => place()}
          >
            {placeStatus === 'pending' ? 'Placing…' : 'Confirm & place order'}
          </button>
          <button
            className="btn-secondary mt-2 disabled:opacity-50"
            disabled={saveStatus === 'pending'}
            onClick={() => save()}
          >
            {saveStatus === 'pending'
              ? 'Saving…'
              : saveStatus === 'success'
                ? '✓ Saved — close this tab to return to chat'
                : 'Save & continue later'}
          </button>
        </div>
      </div>
    </div>
  );
}
