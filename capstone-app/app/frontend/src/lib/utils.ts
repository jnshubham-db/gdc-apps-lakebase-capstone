import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Compact currency for LTV / spend readouts. */
export function usd(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

/** Churn score → semantic band. Never rely on hue alone (a11y). */
export type RiskBand = "ok" | "watch" | "alert";
export function churnBand(score: number | null | undefined): RiskBand {
  if (score == null) return "ok";
  if (score >= 0.66) return "alert";
  if (score >= 0.33) return "watch";
  return "ok";
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
