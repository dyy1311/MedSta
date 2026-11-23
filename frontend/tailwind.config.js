/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#0E7490",
          dark: "#164E63",
          hover: "#155E75",
          soft: "#ECFEFF",
          cyan: "#0891B2",
        },
        surface: {
          page: "#F3F7F6",
          card: "#FFFFFF",
          raised: "#F8FBFA",
        },
        ink: {
          DEFAULT: "#164E63",
          muted: "#3F5E6B",
          faint: "#5F7C88",
        },
        ok: "#047857",
        danger: "#B91C1C",
        warn: "#C2410C",
      },
      fontFamily: {
        sans: [
          "Figtree",
          "'Noto Sans SC'",
          "'PingFang SC'",
          "'Noto Sans CJK SC'",
          "'Microsoft YaHei'",
          "sans-serif",
        ],
        display: ["Figtree", "'Noto Sans SC'", "'PingFang SC'", "'Microsoft YaHei'", "sans-serif"],
      },
      letterSpacing: {
        tightest: "-0.02em",
      },
      boxShadow: {
        xs: "0 1px 2px rgba(26, 29, 43, 0.05)",
        sm: "0 1px 3px rgba(30, 42, 90, 0.07), 0 1px 2px rgba(30, 42, 90, 0.04)",
        card: "0 2px 12px rgba(30, 42, 90, 0.07)",
        hover: "0 8px 24px rgba(59, 91, 219, 0.14), 0 2px 6px rgba(30, 42, 90, 0.06)",
        pop: "0 16px 40px rgba(30, 42, 90, 0.16), 0 4px 12px rgba(30, 42, 90, 0.08)",
      },
      borderRadius: {
        xl: "0.875rem",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        breathe: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.35s ease-out both",
        "fade-in-up-lg": "fade-in-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        breathe: "breathe 1.6s ease-in-out infinite",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
