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
        background: '#080b10',
        sidebar: '#0b0f15',
        surface: {
          DEFAULT: '#0f141c',
          raised: '#151d28',
          elevated: '#1a2431',
          input: '#0b0f16',
        },
        border: {
          subtle: '#18202c',
          DEFAULT: '#263242',
          hover: '#3d4f66',
        },
        text: {
          primary: '#edf2f7',
          secondary: '#a0acba',
          muted: '#687789',
        },
        accent: {
          cyan: '#53d9f2',
          blue: '#648bff',
          violet: '#9681f5',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          '"Cascadia Code"',
          '"Fira Code"',
          'Consolas',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
}
