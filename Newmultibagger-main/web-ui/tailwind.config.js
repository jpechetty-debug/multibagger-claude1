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
          bg: '#04060d',
          card: '#080c17',
          border: 'rgba(255, 255, 255, 0.05)',
          accent: '#00ffa3',
          rose: '#ff3060',
          gold: '#ffb700',
          text: '#c9d4f0',
          'text-dim': '#6d7fa8',
        }
      },
      fontFamily: {
        display: ["Syne", "sans-serif"],
        mono: ["Geist Mono", "monospace"],
        sans: ["Geist", "sans-serif"],
      }
    },
  },
  plugins: [],
}
