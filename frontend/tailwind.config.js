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
          50:  '#e8e6e3', // primary text
          100: '#d4d0cb',
          200: '#b5b0a8', // secondary text
          300: '#9a9590', // muted text
          400: '#6e6a65', // faint text
          500: '#4a4743',
          600: '#403d39', // active states
          700: '#363330', // hover backgrounds
          800: '#2c2925', // borders / elevated
          900: '#211f1c', // sidebar / surface
          950: '#1a1815', // main canvas
        },
        rust: {
          DEFAULT: '#d97757',
          400: '#e09070',
          500: '#d97757',
          600: '#c4674a',
        },
        sand: {
          50:  '#faf8f5', // warm white - page backgrounds
          100: '#f5f2ed', // elevated surfaces
          200: '#e8e4de', // borders, dividers
          300: '#d4cfc7', // heavier borders
          400: '#a8a299', // muted text, placeholders
          500: '#7a746b', // medium emphasis
          600: '#5c5750', // secondary text
          700: '#443f39', // body text
          800: '#2d2923', // strong text
          900: '#1c1917', // headings
          950: '#0f0e0c', // max contrast
        },
      },
    },
  },
  plugins: [
    require('tailwind-scrollbar'),
    require('@tailwindcss/typography'),
  ],
}
