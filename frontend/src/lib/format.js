/**
 * Display formatters
 **/
/**
 * Format an E.164 phone number for readable display.
 *
 *   +919999912345  →  "+91 99999 12345"
 *   +14155238886   →  "+1 415 523 8886"
 *   "blah"         →  "blah"   (unrecognised → returned as-is)
 *
 * We don't pull in libphonenumber — overkill for a one-format display
 * tweak. This handles India (+91, 10-digit body) and US/Canada (+1,
 * 10-digit body) specifically; other countries fall back to "+<cc> <body>".
 **/
export function formatPhone(raw) {
  if (!raw || typeof raw !== 'string') return raw ?? '';

  const cleaned = raw.replace(/\s+/g, '');
  if (!cleaned.startsWith('+')) return raw; // Not E.164 — return as-is

  // India: +91 XXXXX XXXXX  (5+5 split is the standard Indian convention)
  if (cleaned.startsWith('+91') && cleaned.length === 13) {
    const body = cleaned.slice(3);
    return `+91 ${body.slice(0, 5)} ${body.slice(5)}`;
  }

  // US/Canada: +1 XXX XXX XXXX
  if (cleaned.startsWith('+1') && cleaned.length === 12) {
    const body = cleaned.slice(2);
    return `+1 ${body.slice(0, 3)} ${body.slice(3, 6)} ${body.slice(6)}`;
  }

  // Generic fallback: assume 2- or 3-char country code, space before body
  const match = cleaned.match(/^\+(\d{1,3})(.*)$/);
  if (match) return `+${match[1]} ${match[2]}`;

  return raw;
}

/**
 * Format a snake_case unit label for display.
 *
 *   "half_kg"  →  "Half Kg"
 *   "kg"       →  "Kg"
 *   "piece"    →  "Piece"
 *   "loaf"     →  "Loaf"
 *
 * Splits on underscores, capitalises each word, rejoins with spaces.
 * Used for product unit display (replaces raw DB values like "half_kg"
 * appearing in the UI).
 */
export function formatUnitLabel(raw) {
  if (!raw || typeof raw !== 'string') return raw ?? '';
  return raw
    .split('_')
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1).toLowerCase() : part))
    .join(' ');
}

/**
 * Format a number as INR currency with the ₹ symbol and 2 decimal places.
 *
 *   742  →  "₹742.00"
 *   84.5 →  "₹84.50"
 *
 * Used to standardise currency display across Orders, Dashboard, and the
 * Order detail panel. Avoids the pattern of `₹${Number(x).toFixed(2)}`
 * repeated across files.
 */
export function formatINR(amount) {
  if (amount === null || amount === undefined) return '—';
  const n = Number(amount);
  if (Number.isNaN(n)) return '—';
  return `₹${n.toFixed(2)}`;
}
