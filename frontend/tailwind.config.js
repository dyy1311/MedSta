/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#3B5BDB",
          dark: "#1E2A5A",
          cyan: "#22B8CF",
        },
        surface: {
          page: "#F7F8FB",
          card: "#FFFFFF",
        },
        ink: {
          DEFAULT: "#1A1D2B",
          muted: "#6B7280",
        },
        ok: "#2F9E44",
        danger: "#E03131",
        warn: "#F08C00",
      },
      fontFamily: {
        sans: ["'PingFang SC'", "'Microsoft YaHei'", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 2px 12px rgba(30, 42, 90, 0.08)",
        hover: "0 6px 20px rgba(59, 91, 219, 0.15)",
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
      },
      animation: {
        "fade-in-up": "fade-in-up 0.35s ease-out both",
        breathe: "breathe 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
