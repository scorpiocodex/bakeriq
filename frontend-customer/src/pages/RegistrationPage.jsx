import { useParams } from 'react-router-dom';
import { useRegistration } from '../hooks/useRegistration';

export default function RegistrationPage() {
  const { token } = useParams();
  const {
    status,
    tokenData,
    form,
    setField,
    submit,
    submitError,
    loadError,
    isSubmitting,
    submittedResult,
  } = useRegistration(token);

  // ============================================================
  // Loading state — GET in flight
  // ============================================================
  if (status === 'loading') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <p className="text-gray-600">Loading…</p>
      </div>
    );
  }

  // ============================================================
  // Error state — token invalid/consumed/expired
  // ============================================================
  if (status === 'error') {
    // Distinguish 404 (not found) from 410 (consumed/expired) for
    // more actionable messaging.
    const httpStatus = loadError?.response?.status;
    const detail = loadError?.response?.data?.detail;

    let title, message;
    if (httpStatus === 410) {
      title = 'This link is no longer valid';
      message =
        detail ||
        'The registration link has expired or has already been used. ' +
          'Please message BakeriQ on WhatsApp to get a fresh link.';
    } else if (httpStatus === 404) {
      title = 'Link not found';
      message =
        'This registration link is invalid. ' +
        'Please message BakeriQ on WhatsApp to get a valid link.';
    } else {
      title = 'Something went wrong';
      message =
        'We couldn’t load this registration link. Please try again in a moment, ' +
        'or contact BakeriQ on WhatsApp.';
    }

    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-red-200 p-4">
          <p className="font-semibold text-red-700">{title}</p>
          <p className="text-sm text-gray-700 mt-2">{message}</p>
        </div>
      </div>
    );
  }

  // ============================================================
  // Already registered — GET returned already_registered: true
  // ============================================================
  if (status === 'already_registered') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-brand-200 p-6 text-center">
          <p className="text-2xl mb-2">✓</p>
          <p className="font-semibold text-gray-900">You’re already registered!</p>
          <p className="text-sm text-gray-600 mt-2">
            You can close this page and message BakeriQ on WhatsApp to place an order.
          </p>
        </div>
      </div>
    );
  }

  // ============================================================
  // Submitted state — POST returned success
  // ============================================================
  if (status === 'submitted') {
    return (
      <div className="app-container">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        </header>
        <div className="bg-white rounded-lg shadow-sm border border-brand-200 p-6 text-center">
          <p className="text-2xl mb-2">✓</p>
          <p className="font-semibold text-gray-900">Registration submitted!</p>
          <p className="text-sm text-gray-600 mt-3">
            {submittedResult?.message ||
              "You'll get a WhatsApp message once the bakery owner approves you."}
          </p>
          <p className="text-sm text-gray-600 mt-3">
            You can close this page and return to WhatsApp.
          </p>
        </div>
      </div>
    );
  }

  // ============================================================
  // Ready — render the form
  // ============================================================

  // Distinguish submit errors from load errors for inline messaging
  const submitStatus = submitError?.response?.status;
  const submitDetail = submitError?.response?.data?.detail;

  let submitErrorMessage = null;
  if (submitError) {
    if (submitStatus === 410) {
      submitErrorMessage =
        submitDetail ||
        'This link expired while you were filling out the form. Please message BakeriQ for a fresh link.';
    } else if (submitStatus === 409) {
      submitErrorMessage = submitDetail || 'This phone is already registered with BakeriQ.';
    } else if (submitStatus === 422) {
      // Pydantic validation — extract the first error
      const errors = submitError.response.data?.detail;
      const firstError = Array.isArray(errors) && errors[0];
      submitErrorMessage = firstError
        ? `${firstError.loc?.[1] || 'Field'}: ${firstError.msg}`
        : 'Please check the form and try again.';
    } else {
      submitErrorMessage =
        submitDetail || 'Something went wrong submitting your registration. Please try again.';
    }
  }

  const canSubmit = form.name.trim().length > 0 && !isSubmitting;

  function handleSubmit(e) {
    e.preventDefault();
    if (canSubmit) {
      submit().catch(() => {
        // Error already captured in submitError; nothing extra to do
      });
    }
  }

  return (
    <div className="app-container pb-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-brand-700">BakeriQ</h1>
        <p className="mt-1 text-sm text-gray-600">
          Just a few details and the bakery owner will approve you shortly.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-lg shadow-sm border border-brand-100 p-4 space-y-4"
      >
        {/* Phone — read-only, pre-filled */}
        <div>
          <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-1">
            Phone (from WhatsApp)
          </label>
          <input
            id="phone"
            type="text"
            value={tokenData.phone}
            readOnly
            className="w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600 cursor-not-allowed"
          />
        </div>

        {/* Name — required */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Full name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={form.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="e.g. Anita Kumar"
            required
            maxLength={100}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Address line 1 */}
        <div>
          <label htmlFor="address_line_1" className="block text-sm font-medium text-gray-700 mb-1">
            Address line 1
          </label>
          <input
            id="address_line_1"
            type="text"
            value={form.address_line_1}
            onChange={(e) => setField('address_line_1', e.target.value)}
            placeholder="e.g. 12 MG Road"
            maxLength={200}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Address line 2 */}
        <div>
          <label htmlFor="address_line_2" className="block text-sm font-medium text-gray-700 mb-1">
            Address line 2 (optional)
          </label>
          <input
            id="address_line_2"
            type="text"
            value={form.address_line_2}
            onChange={(e) => setField('address_line_2', e.target.value)}
            placeholder="e.g. Near Kadavanthra Junction"
            maxLength={200}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* City + State — side by side on wider screens */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="city" className="block text-sm font-medium text-gray-700 mb-1">
              City
            </label>
            <input
              id="city"
              type="text"
              value={form.city}
              onChange={(e) => setField('city', e.target.value)}
              placeholder="Kochi"
              maxLength={100}
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
          <div>
            <label htmlFor="state" className="block text-sm font-medium text-gray-700 mb-1">
              State
            </label>
            <input
              id="state"
              type="text"
              value={form.state}
              onChange={(e) => setField('state', e.target.value)}
              placeholder="Kerala"
              maxLength={100}
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>

        {/* Pincode */}
        <div>
          <label htmlFor="pincode" className="block text-sm font-medium text-gray-700 mb-1">
            Pincode
          </label>
          <input
            id="pincode"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={form.pincode}
            onChange={(e) => {
              const digitsOnly = e.target.value.replace(/\D/g, '').slice(0, 6);
              setField('pincode', digitsOnly);
            }}
            placeholder="682020"
            maxLength={6}
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Submit error — inline banner above the button */}
        {submitErrorMessage && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2">
            <p className="text-sm text-red-700">{submitErrorMessage}</p>
          </div>
        )}

        {/* Submit button */}
        <button
          type="submit"
          disabled={!canSubmit}
          className="btn-primary w-full disabled:opacity-50"
        >
          {isSubmitting ? 'Submitting…' : 'Submit registration'}
        </button>

        <p className="text-xs text-gray-500 text-center mt-2">
          The bakery owner will review and approve you. You'll get a WhatsApp message when you're
          approved.
        </p>
      </form>
    </div>
  );
}
