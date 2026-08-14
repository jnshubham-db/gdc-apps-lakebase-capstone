import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";
import { churnBand, type RiskBand } from "@/lib/utils";

// --- Button — instrument-panel control ------------------------------------

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-display uppercase tracking-[0.14em] text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/70 focus-visible:ring-offset-2 focus-visible:ring-offset-panel disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        // ENGAGE — luminous green fill on press-ready primary action.
        primary:
          "rounded-sm border border-green/60 bg-green/10 text-green hover:bg-green hover:text-panel hover:shadow-glow active:translate-y-px",
        // STANDBY — outlined secondary.
        secondary:
          "rounded-sm border border-bezel bg-face text-lum/80 hover:border-lum/40 hover:text-lum active:translate-y-px",
        ghost: "rounded-sm text-muted hover:text-lum hover:bg-face",
      },
      size: { md: "h-10 px-5", sm: "h-8 px-3 text-xs", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

// --- Panel — brushed-bezel raised surface ---------------------------------

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bezel relative", className)} {...props} />;
}

export function PanelHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-bezel px-4 py-3",
        className,
      )}
      {...props}
    />
  );
}

// --- Caution lamp — lights only on deviation (amber/alert) -----------------

const LAMP = {
  ok: { on: false, cls: "border-bezel text-muted", label: "OK" },
  watch: { on: true, cls: "border-amber/60 text-amber bg-amber/10 shadow-glow-amber", label: "WATCH" },
  alert: { on: true, cls: "border-alert/60 text-alert bg-alert/10 shadow-glow-alert", label: "ALERT" },
} as const;

export function CautionLamp({ band, children }: { band: RiskBand; children?: React.ReactNode }) {
  const l = LAMP[band];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-display text-[11px] uppercase tracking-[0.14em]",
        l.cls,
      )}
    >
      <span
        className={cn("h-1.5 w-1.5 rounded-full", l.on ? "bg-current" : "bg-muted/40")}
        aria-hidden
      />
      {children ?? l.label}
    </span>
  );
}

// --- Churn readout — number + band, hue never the only signal --------------

export function ChurnReadout({ score }: { score: number | null | undefined }) {
  const band = churnBand(score);
  const glyph = band === "alert" ? "▲" : band === "watch" ? "▴" : "·";
  const color = band === "alert" ? "text-alert" : band === "watch" ? "text-amber" : "text-muted";
  return (
    <span className={cn("readout inline-flex items-center gap-1.5", color)}>
      <span aria-hidden>{glyph}</span>
      {score == null ? "—" : score.toFixed(2)}
    </span>
  );
}

// --- Linear meter (LTV bar in the table) -----------------------------------

export function Meter({ frac, tone = "green" }: { frac: number; tone?: "green" | "amber" }) {
  const c = tone === "amber" ? "#FFB000" : "#39FF9A";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-sm bg-bezel">
      <div
        className="h-full rounded-sm transition-[width] duration-500"
        style={{
          width: `${Math.max(2, Math.min(100, frac * 100))}%`,
          background: c,
          boxShadow: `0 0 6px ${c}88`,
        }}
      />
    </div>
  );
}
