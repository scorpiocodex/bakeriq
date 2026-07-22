/**
 * Format a rupee amount. Indian formatting style (no commas for
 * sub-1000 values; comma separator at 1000+ when needed).
 *
 * Money values from the API arrive as plain numbers (e.g. 84.0 for
 * ₹84). We round to whole rupees for display — the bakery doesn't
 * use paise in practice.
 */
export function formatRupees(amount) {
  if (amount == null) return '—';
  return `₹${Math.round(amount).toLocaleString('en-IN')}`;
}
