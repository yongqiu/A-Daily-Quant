/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ========================================
        // CYBERPUNK TECH THEME V2.0
        // 更强科技感的配色方案
        // ========================================

        // Deep Space Backgrounds
        bg: {
          DEFAULT: '#050508',        // Deep void black
          elevated: '#0a0d12',       // Surface elevated
          card: '#0f1218',           // Card background
          cardHover: '#14181f',      // Card hover state
          input: '#0a0d12',          // Input background
        },

        // Border System - Subtle tech glow
        border: {
          DEFAULT: 'rgba(255, 255, 255, 0.06)',
          subtle: 'rgba(255, 255, 255, 0.04)',
          medium: 'rgba(255, 255, 255, 0.10)',
          strong: 'rgba(255, 255, 255, 0.15)',
          // Tech accent borders
          primary: 'rgba(99, 102, 241, 0.3)',
          success: 'rgba(34, 197, 94, 0.3)',
          warning: 'rgba(251, 191, 36, 0.3)',
          danger: 'rgba(239, 68, 68, 0.3)',
        },

        // Text Hierarchy - Enhanced readability
        text: {
          DEFAULT: '#c4c9d4',
          primary: '#f1f5f9',        // High contrast primary
          secondary: '#a1a8b6',      // Secondary text
          tertiary: '#6b7280',       // Tertiary/muted
          inverted: '#050508',       // Text on colored bg
        },

        // ========================================
        // ACCENT COLORS - Cyberpunk Neon Palette
        // ========================================

        // Primary - Electric Indigo
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          DEFAULT: '#6366f1',       // Main brand color
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
          glow: 'rgba(99, 102, 241, 0.15)',
        },

        // Market Colors - Enhanced neon
        up: {
          DEFAULT: '#ef4444',        // Chinese red for up
          50: '#fef2f2',
          100: '#fee2e2',
          200: '#fecaca',
          300: '#fca5a5',
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
          700: '#b91c1c',
          800: '#991b1b',
          900: '#7f1d1d',
          dim: 'rgba(239, 68, 68, 0.1)',
          glow: 'rgba(239, 68, 68, 0.2)',
        },

        down: {
          DEFAULT: '#22c55e',        // Green for down
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
          dim: 'rgba(34, 197, 94, 0.1)',
          glow: 'rgba(34, 197, 94, 0.2)',
        },

        // Semantic Colors
        success: {
          DEFAULT: '#10b981',
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
          dim: 'rgba(16, 185, 129, 0.1)',
        },

        warning: {
          DEFAULT: '#f59e0b',
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
          950: '#451a03',
          dim: 'rgba(245, 158, 11, 0.1)',
        },

        danger: {
          DEFAULT: '#f43f5e',
          50: '#fff1f2',
          100: '#ffe4e6',
          200: '#fecdd3',
          300: '#fda4af',
          400: '#fb7185',
          500: '#f43f5e',
          600: '#e11d48',
          700: '#be123c',
          800: '#9f1239',
          900: '#881337',
          950: '#4c0519',
          dim: 'rgba(244, 63, 94, 0.1)',
        },

        info: {
          DEFAULT: '#3b82f6',
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
          950: '#172554',
          dim: 'rgba(59, 130, 246, 0.1)',
        },

        // Special Tech Accents
        cyan: {
          DEFAULT: '#06b6d4',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          glow: 'rgba(6, 182, 212, 0.15)',
        },

        purple: {
          DEFAULT: '#a855f7',
          400: '#c084fc',
          500: '#a855f7',
          600: '#9333ea',
          glow: 'rgba(168, 85, 247, 0.15)',
        },

        // Legacy compatibility (deprecated, use above instead)
        navy: {
          deep: '#050508',
          mid: '#0a0d12',
          light: '#0f1218',
        },
        data: {
          blue: '#3b82f6',
          dim: 'rgba(59, 130, 246, 0.1)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'Courier New', 'monospace'],
        display: ['Inter', 'system-ui', 'sans-serif'],
      },

      // ========================================
      // CYBERPUNK BACKGROUNDS & PATTERNS
      // ========================================
      backgroundImage: {
        // Grid patterns for tech aesthetic
        'grid-pattern': `linear-gradient(to right, rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                          linear-gradient(to bottom, rgba(255, 255, 255, 0.03) 1px, transparent 1px)`,
        'grid-pattern-lg': `linear-gradient(to right, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
                             linear-gradient(to bottom, rgba(255, 255, 255, 0.05) 1px, transparent 1px)`,

        // Gradient overlays
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',

        // Tech glow backgrounds
        'glow-primary': 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(99, 102, 241, 0) 100%)',
        'glow-success': 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0) 100%)',
        'glow-danger': 'linear-gradient(135deg, rgba(244, 63, 94, 0.1) 0%, rgba(244, 63, 94, 0) 100%)',
        'glow-cyan': 'linear-gradient(135deg, rgba(6, 182, 212, 0.1) 0%, rgba(6, 182, 212, 0) 100%)',
        'glow-purple': 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(168, 85, 247, 0) 100%)',

        // Subtle mesh gradient
        'mesh-gradient': `radial-gradient(at 40% 20%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
                          radial-gradient(at 80% 0%, rgba(6, 182, 212, 0.06) 0px, transparent 50%),
                          radial-gradient(at 0% 50%, rgba(168, 85, 247, 0.05) 0px, transparent 50%),
                          radial-gradient(at 80% 50%, rgba(16, 185, 129, 0.05) 0px, transparent 50%),
                          radial-gradient(at 0% 100%, rgba(244, 63, 94, 0.05) 0px, transparent 50%)`,
      },

      backgroundSize: {
        'grid-base': '24px 24px',
        'grid-lg': '48px 48px',
      },

      // ========================================
      // TECH SHADOWS & GLOWS
      // ========================================
      boxShadow: {
        // Base shadows
        'sm': '0 1px 2px 0 rgba(0, 0, 0, 0.3)',
        'DEFAULT': '0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.3)',
        'md': '0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3)',
        'lg': '0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.4)',
        'xl': '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4)',

        // Card-specific shadows
        'card': '0 2px 8px rgba(0, 0, 0, 0.3), 0 1px 3px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 8px 24px rgba(0, 0, 0, 0.4), 0 2px 6px rgba(0, 0, 0, 0.3)',
        'card-elevated': '0 12px 32px rgba(0, 0, 0, 0.5), 0 4px 12px rgba(0, 0, 0, 0.4)',

        // Glow effects
        'glow-primary': '0 0 20px rgba(99, 102, 241, 0.3), 0 0 40px rgba(99, 102, 241, 0.1)',
        'glow-success': '0 0 20px rgba(16, 185, 129, 0.3), 0 0 40px rgba(16, 185, 129, 0.1)',
        'glow-danger': '0 0 20px rgba(244, 63, 94, 0.3), 0 0 40px rgba(244, 63, 94, 0.1)',
        'glow-cyan': '0 0 20px rgba(6, 182, 212, 0.3), 0 0 40px rgba(6, 182, 212, 0.1)',
        'glow-purple': '0 0 20px rgba(168, 85, 247, 0.3), 0 0 40px rgba(168, 85, 247, 0.1)',

        // Inner shadows for inputs
        'inner-light': 'inset 0 1px 2px rgba(255, 255, 255, 0.05)',
        'inner-dark': 'inset 0 2px 4px rgba(0, 0, 0, 0.3)',

        // Tech border glow
        'border-glow': '0 0 0 1px rgba(99, 102, 241, 0.3), 0 0 20px rgba(99, 102, 241, 0.1)',
      },

      // ========================================
      // CYBERPUNK ANIMATIONS
      // ========================================
      animation: {
        // Pulse variations
        'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',

        // Spin
        'spin': 'spin 1s linear infinite',
        'spin-slow': 'spin 2s linear infinite',

        // Flash effects for price updates
        'flash-up': 'flashUp 0.6s ease-out',
        'flash-down': 'flashDown 0.6s ease-out',

        // Glow pulsing
        'glow': 'glow 2s ease-in-out infinite alternate',
        'glow-slow': 'glow 3s ease-in-out infinite alternate',

        // Shimmer for loading states
        'shimmer': 'shimmer 2s linear infinite',

        // Slide animations
        'slide-in': 'slideIn 0.3s ease-out',
        'slide-out': 'slideOut 0.2s ease-in',

        // Fade animations
        'fade-in': 'fadeIn 0.2s ease-out',
        'fade-out': 'fadeOut 0.2s ease-in',

        // Scale animations
        'scale-in': 'scaleIn 0.2s ease-out',
        'scale-out': 'scaleOut 0.2s ease-in',

        // Bounce for attention
        'bounce-subtle': 'bounceSubtle 0.5s ease-out',

        // Scanline for tech effect
        'scanline': 'scanline 8s linear infinite',
      },

      keyframes: {
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        spin: {
          'from': { transform: 'rotate(0deg)' },
          'to': { transform: 'rotate(360deg)' },
        },
        flashUp: {
          '0%': { backgroundColor: 'rgba(239, 68, 68, 0.3)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashDown: {
          '0%': { backgroundColor: 'rgba(34, 197, 94, 0.3)' },
          '100%': { backgroundColor: 'transparent' },
        },
        glow: {
          '0%': {
            boxShadow: '0 0 5px rgba(99, 102, 241, 0.2), 0 0 10px rgba(99, 102, 241, 0.1)',
          },
          '100%': {
            boxShadow: '0 0 20px rgba(99, 102, 241, 0.4), 0 0 40px rgba(99, 102, 241, 0.2)',
          },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideOut: {
          '0%': { transform: 'translateY(0)', opacity: '1' },
          '100%': { transform: 'translateY(-10px)', opacity: '0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeOut: {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        scaleOut: {
          '0%': { transform: 'scale(1)', opacity: '1' },
          '100%': { transform: 'scale(0.95)', opacity: '0' },
        },
        bounceSubtle: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
      },

      // ========================================
      // ENHANCED SPACING & SIZING
      // ========================================
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '92': '23rem',
        '96': '24rem',
        '100': '25rem',
        '104': '26rem',
        '108': '27rem',
        '112': '28rem',
        '116': '29rem',
        '120': '30rem',
        '124': '31rem',
        '128': '32rem',
        '132': '33rem',
        '136': '34rem',
        '140': '35rem',
        '144': '36rem',
      },

      // ========================================
      // BORDER RADIUS FOR TECH LOOK
      // ========================================
      borderRadius: {
        '4xl': '2rem',
        '5xl': '2.5rem',
      },

      // ========================================
      // Z-INDEX SCALE
      // ========================================
      zIndex: {
        '60': '60',
        '70': '70',
        '80': '80',
        '90': '90',
        '100': '100',
      },

      // ========================================
      // TRANSITION DURATIONS
      // ========================================
      transitionDuration: {
        '400': '400ms',
        '600': '600ms',
        '800': '800ms',
      },
    },
  },
  plugins: [],
}
