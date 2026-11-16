/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#3B5BDB",
          dark: "#1E2A5A",
          hover: "#3350C4",
          soft: "#E6EBFB",
          cyan: "#22B8CF",
        },
        surface: {
          page: "#F6F7FA",
          card: "#FFFFFF",
          raised: "#FBFBFD",
        },
        ink: {
          DEFAULT: "#1A1D2B",
          muted: "#6B7280",
          faint: "#9AA1B0",
        },
        ok: "#2F9E44",
        danger: "#E03131",
        warn: "#F08C00",
      },
      fontFamily: {
        sans: [
          "'PingFang SC'",
          "'HarmonyOS Sans SC'",
          "'Microsoft YaHei'",
          "system-ui",
          "sans-serif",
        ],
        // 数字与西文展示字体（统计工具的排印核心：等宽数字 + 工程感字标）
        display: ["'Space Grotesk'", "'PingFang SC'", "'Microsoft YaHei'", "sans-serif"],
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
