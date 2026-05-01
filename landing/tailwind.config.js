/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        warm: {
          50:  '#e8e6e3',
          100: '#d4d0cb',
          200: '#b5b0a8',
          300: '#9a9590',
          400: '#6e6a65',
          500: '#4a4743',
          600: '#403d39',
          700: '#363330',
          800: '#2c2925',
          900: '#211f1c',
          950: '#1a1815',
        },
        rust: {
          DEFAULT: '#d97757',
          400: '#e09070',
          500: '#d97757',
          600: '#c4674a',
        },
        sand: {
          50:  '#faf8f5',
          100: '#f5f2ed',
          200: '#e8e4de',
          300: '#d4cfc7',
          400: '#a8a299',
          500: '#7a746b',
          600: '#5c5750',
          700: '#443f39',
          800: '#2d2923',
          900: '#1c1917',
          950: '#0f0e0c',
        },
      },
    },
  },
  plugins: [
    require('tailwind-scrollbar'),
    require('@tailwindcss/typography'),
  ],
}
