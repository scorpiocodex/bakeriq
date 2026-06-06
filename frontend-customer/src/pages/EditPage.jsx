import { useParams } from 'react-router-dom';

export default function EditPage() {
  const { token } = useParams();

  return (
    <div className="app-container">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        <p className="mt-1 text-sm text-gray-600">Edit your cart</p>
      </header>

      <div className="bg-white rounded-lg shadow-sm border border-brand-100 p-4">
        <p className="text-sm text-gray-500 mb-2">Token:</p>
        <p className="font-mono text-xs text-gray-900 break-all">{token}</p>
        <p className="mt-4 text-sm text-gray-600">
          Your in-progress cart will be loaded so you can keep editing. Coming together in Task 5.
        </p>
      </div>

      <button className="btn-primary mt-6" disabled>
        Save & return to chat
      </button>
    </div>
  );
}
