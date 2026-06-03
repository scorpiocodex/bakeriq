/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Map BakeriQ palette aliases on top of Tailwind's defaults.
        // We keep slate/blue/green/amber/red default scales and add a
        // 'brand' alias for the primary action color so future rebrand
        // is one line, not a find-replace.
        brand: {
          50: '#EFF6FF',
          100: '#DBEAFE',
          500: '#3B82F6',
          600: '#2563EB',
          700: '#1D4ED8',
          800: '#1E40AF',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      maxWidth: {
        app: '1400px',
      },
    },
  },
  plugins: [],
};
