/**
 * CylinGuard design tokens.
 *
 * This file is the design system, not a formality. `postcss.config.js` already loads
 * the Tailwind plugin, so until this existed with a `content` glob Tailwind emitted no
 * utilities at all and `npm run build` could not produce a usable stylesheet.
 *
 * Two rules shaped the palette.
 *
 * **Contrast is structural, not a later pass (spec §59).** Every colour below that
 * carries text or conveys a state was checked against the `base` background: the
 * state colours land between 7:1 and 12:1, and `text-muted` at 8.6:1, all comfortably
 * past the 4.5:1 AA threshold. That is why the state colours are the lighter 400-level
 * variants rather than the saturated 500/600 ones that look better on white.
 *
 * **Colour is never the only signal.** A green dot always carries the word SAFE
 * beside it, so these tokens are paired with a label in `StatusBadge` rather than used
 * alone. Anyone reading a status by hue only - colour-blind, glare on a phone, a
 * projector at a demo - still gets the state.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Base surfaces, darkest to lightest. `base` matches the theme-color in
        // index.html so the mobile browser chrome blends into the page.
        base: '#060B18',
        surface: {
          DEFAULT: '#0D1526',
          raised: '#141F36',
          overlay: '#1B2847',
        },
        // Thin hairlines rather than heavy boxes - the glass look depends on the
        // border being barely there.
        hairline: 'rgba(255, 255, 255, 0.08)',
        'hairline-strong': 'rgba(255, 255, 255, 0.16)',

        ink: {
          DEFAULT: '#E8EEF9', // primary text, 15.8:1 on base
          muted: '#9BABC7', //  secondary text, 8.6:1 on base
          faint: '#64748B', //  non-essential only; never the sole carrier of meaning
        },

        // Neon blue accent (spec §9).
        accent: {
          DEFAULT: '#38BDF8', // 9.5:1 on base
          soft: 'rgba(56, 189, 248, 0.12)',
          ring: 'rgba(56, 189, 248, 0.45)',
        },

        // State colours. Always rendered with an icon and a word.
        safe: { DEFAULT: '#34D399', soft: 'rgba(52, 211, 153, 0.12)' }, // 11:1
        warn: { DEFAULT: '#FBBF24', soft: 'rgba(251, 191, 36, 0.12)' }, // 12:1
        danger: { DEFAULT: '#F87171', soft: 'rgba(248, 113, 113, 0.14)' }, // 7:1
        demo: { DEFAULT: '#C4B5FD', soft: 'rgba(196, 181, 253, 0.14)' }, // simulated data
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        // Weights and gas values are read as digits and compared down a column, so
        // they get tabular figures.
        mono: ['JetBrains Mono', 'Consolas', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        glass: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 32px -12px rgba(0,0,0,0.6)',
        'glow-accent': '0 0 0 1px rgba(56,189,248,0.35), 0 8px 28px -10px rgba(56,189,248,0.35)',
        'glow-danger': '0 0 0 1px rgba(248,113,113,0.4), 0 8px 28px -10px rgba(248,113,113,0.45)',
      },
      borderRadius: { xl2: '1.125rem' },
      keyframes: {
        // Used by the emergency banner. Opacity only - a pulse that moves layout
        // makes text hard to read, and `motion-reduce` turns it off entirely.
        'pulse-alarm': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
        'fade-in-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'pulse-alarm': 'pulse-alarm 1.6s ease-in-out infinite',
        'fade-in-up': 'fade-in-up 0.22s ease-out both',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
}
