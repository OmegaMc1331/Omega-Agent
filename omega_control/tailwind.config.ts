import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        omega: {
          bg: '#101114',
          panel: '#181a1f',
          card: '#202329',
          line: '#30343c',
          text: '#f5f7fb',
          muted: '#a5adba',
          green: '#62c5aa',
          amber: '#e3b15f',
          red: '#e86f6f',
        },
      },
      boxShadow: {
        panel: '0 14px 34px rgba(0,0,0,0.18)',
        soft: '0 10px 28px rgba(0,0,0,0.18)',
        'inset-line': 'inset 0 1px 0 rgba(255,255,255,0.055)',
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out both',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
