/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          bg: '#0F172A',
          card: 'rgba(30, 41, 59, 0.5)',
          border: 'rgba(255, 255, 255, 0.1)',
          primary: '#F59E0B',
          secondary: '#06B6D4',
          accent: '#FBBF24',
          rose: '#EF4444',
          emerald: '#10B981',
          text: '#F8FAFC',
          'text-dim': '#94A3B8',
        }
      },
      fontFamily: {
        display: ["Fira Code", "monospace"],
        mono: ["Fira Code", "monospace"],
        sans: ["Fira Sans", "sans-serif"],
      }
    },
  },
  plugins: [],
}
