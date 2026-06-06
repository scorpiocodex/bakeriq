/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // BakeriQ brand palette - matches the owner dashboard
        brand: {
          50: '#fef7ed',
          100: '#fdecd4',
          200: '#fad6a8',
          300: '#f6b771',
          400: '#f19638',
          500: '#ec7a18',
          600: '#dd610e', // primary brand colour — warm bakery orange
          700: '#b7480e',
          800: '#923b14',
          900: '#763213',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      maxWidth: {
        // Customer web app is mobile-first; we cap content at this
        // width on tablet/desktop so it doesn't sprawl. The owner
        // dashboard uses 1400px for desktop-first; this app opens
        // inside the WhatsApp in-app browser → assume small screens.
        app: '480px',
      },
    },
  },
  plugins: [],
};
