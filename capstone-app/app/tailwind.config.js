/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./frontend/index.html", "./frontend/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Night-flight instrument panel palette.
        panel: "#0B0D0F", // deepest panel black (page ground)
        face: "#111417", // instrument face / raised surface
        bezel: "#1A1E22", // brushed bezel / borders
        lum: "#F2F5F2", // luminous white (primary text / markings)
        green: "#39FF9A", // radio green (needles, active, primary action)
        amber: "#FFB000", // caution
        alert: "#FF3B30", // alert / high risk
        muted: "#6B7580", // spent-grammar gray (secondary text/ticks)
      },
      fontFamily: {
        display: ['"Saira Condensed"', '"Oswald"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Roboto Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        bezel:
          "inset 0 1px 0 rgba(255,255,255,0.05), inset 0 0 0 1px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.55)",
        glow: "0 0 12px rgba(57,255,154,0.35)",
        "glow-amber": "0 0 12px rgba(255,176,0,0.35)",
        "glow-alert": "0 0 12px rgba(255,59,48,0.4)",
      },
      backgroundImage: {
        // Fine matte-panel texture (subtle radial vignette + grain feel).
        "panel-vignette":
          "radial-gradient(120% 90% at 50% 0%, rgba(255,255,255,0.035) 0%, rgba(0,0,0,0) 55%)",
      },
    },
  },
  plugins: [],
};
