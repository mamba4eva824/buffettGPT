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
        // Value Insights design system (Stitch)
        vi: {
          surface:            '#111125',
          'surface-low':      '#1a1a2e',
          'surface-mid':      '#1e1e32',
          'surface-high':     '#28283d',
          'surface-highest':  '#333348',
          'surface-bright':   '#37374d',
          'surface-lowest':   '#0c0c1f',
          gold:               '#f2c35b',
          'gold-dim':         '#eec058',
          'gold-container':   '#d4a843',
          cream:              '#cac6be',
          sage:               '#a0d6ad',
          'sage-container':   '#86ba93',
          rose:               '#ffb4ab',
          'rose-container':   '#93000a',
          accent:             '#6d28d9',
          'on-surface':       '#e2e0fc',
          'on-surface-variant': '#d2c5b1',
          'on-secondary':     '#b9b5ad',
          outline:            '#9a8f7d',
          'outline-variant':  '#4e4636',
        },
      },
    },
  },
  plugins: [
    require('tailwind-scrollbar'),
    require('@tailwindcss/typography'),
  ],
}
