import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0B0E11",
          card: "#141821",
          elevated: "#1A1F2E",
        },
        border: {
          DEFAULT: "#1E2736",
          light: "#2A3441",
        },
        accent: {
          blue: "#3B82F6",
          green: "#10B981",
          red: "#EF4444",
          yellow: "#F59E0B",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
