import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Magenta directs and does nothing else: the navigation band, the
        // current sub-page, locator tags and next-step signs. Never a state,
        // a chart series or decoration.
        sign: { DEFAULT: "#A3135A", press: "#85104A" },
        ink: { DEFAULT: "#111318", 2: "#3A3D44", 3: "#5C606A" },
        panel: "#16181D",
        ground: "#F4F5F7",
        card: "#FFFFFF",
        concourse: "#E7E9EE",
        rule: "#D3D6DC",
        go: { DEFAULT: "#0A7A3D", bright: "#4BD98A" },
        stop: { DEFAULT: "#C2410C", tint: "#FCE9DF" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      maxWidth: { page: "82.5rem", prose: "68ch" },
    },
  },
  plugins: [],
};

export default config;
