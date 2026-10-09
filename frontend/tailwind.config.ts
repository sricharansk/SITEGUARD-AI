import type { Config } from "tailwindcss";

// Design tokens: see docs/DESIGN_SYSTEM.md. AI-generated content uses the "ai" tone so it is always visually distinct.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#16212b", soft: "#4a5968", faint: "#7a8896" },
        surface: { DEFAULT: "#ffffff", alt: "#f4f6f8", line: "#dde3e9" },
        brand: { DEFAULT: "#0b5cab", dark: "#093f78", tint: "#e6f0fa" },
        ai: { DEFAULT: "#5b3fa6", tint: "#f0ecfa", line: "#cfc4ec" },
      },
    },
  },
  plugins: [],
};
export default config;
