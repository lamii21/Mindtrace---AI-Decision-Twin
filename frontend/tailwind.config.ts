import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#05060a",
          900: "#0a0c14",
          800: "#11141f",
          700: "#191d2c",
          600: "#232840",
        },
        ivory: {
          100: "#faf8f3",
          200: "#f1ede3",
          300: "#e4ddcd",
        },
        lavender: {
          300: "#c9bdf0",
          400: "#ab9aea",
          500: "#8d78e0",
          600: "#6e59c4",
        },
        electric: {
          300: "#9fd4ff",
          400: "#6ab8ff",
          500: "#3b9bff",
          600: "#1f7de0",
        },
        amber: {
          300: "#ffd59e",
          400: "#ffb968",
          500: "#f29a3c",
          600: "#d97d1f",
        },
        coral: {
          400: "#ff9d85",
          500: "#f2765c",
          600: "#d85740",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      backgroundImage: {
        "radial-fade":
          "radial-gradient(60% 60% at 50% 40%, var(--tw-gradient-stops))",
        "atmosphere":
          "radial-gradient(120% 80% at 50% -10%, rgba(141,120,224,0.16), transparent 60%), radial-gradient(90% 60% at 85% 110%, rgba(59,155,255,0.12), transparent 60%)",
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.06) inset, 0 20px 60px -20px rgba(0,0,0,0.6)",
      },
      animation: {
        "fade-up": "fade-up 0.8s cubic-bezier(0.16,1,0.3,1) both",
        "pulse-slow": "pulse-slow 4s ease-in-out infinite",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-slow": {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
