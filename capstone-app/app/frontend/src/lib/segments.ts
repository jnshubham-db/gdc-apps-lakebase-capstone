// Segment names for the filter + override controls. Segments live in gold
// (warehouse-only, not synced to Lakebase), so the app carries the static
// S1–S7 map rather than fetching it. Keep in sync with gold.customer_segments.
export const SEGMENTS: Record<string, string> = {
  S1: "Champions",
  S2: "Loyal",
  S3: "Potential Loyalists",
  S4: "New Customers",
  S5: "At Risk",
  S6: "Hibernating",
  S7: "Price Sensitive",
  S8: "About to Churn",
};

export const SEGMENT_IDS = Object.keys(SEGMENTS);

export function segmentName(id: string | null | undefined): string {
  if (!id) return "—";
  return SEGMENTS[id] ?? id;
}
