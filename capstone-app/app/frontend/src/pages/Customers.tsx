import { ChevronLeft, ChevronRight } from "lucide-react";
import { memo, useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DraftFilters, EMPTY_FILTERS, FilterBar } from "@/components/FilterBar";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button, ChurnReadout, Meter } from "@/components/ui";
import { useCustomers } from "@/lib/queries";
import { segmentName } from "@/lib/segments";
import type { CustomerFilters, CustomerSummary } from "@/lib/types";
import { useDebounced } from "@/lib/useDebounced";
import { churnBand, cn, usd } from "@/lib/utils";

const PAGE_SIZE = 25;
// LTV bar is scaled against a sensible ceiling so the meter is readable.
const LTV_CEILING = 120_000;

export default function Customers() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftFilters>(EMPTY_FILTERS);
  // Keyset pagination: cursors[i] is the `after` cursor used to fetch page i+1
  // (cursors[0] is undefined → page 1). Prev pops, Next pushes next_cursor —
  // so back-navigation replays a cached page and never re-scans with OFFSET.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const debounced = useDebounced(draft, 250);

  const pageNum = cursors.length;
  const after = cursors[cursors.length - 1];

  const filters: CustomerFilters = useMemo(() => {
    const f: CustomerFilters = { page: pageNum, page_size: PAGE_SIZE };
    if (after) f.after = after;
    if (debounced.segment) f.segment = debounced.segment;
    if (debounced.minLtv) f.min_ltv = Number(debounced.minLtv);
    if (debounced.maxChurn) f.max_churn = Number(debounced.maxChurn);
    return f;
  }, [debounced, pageNum, after]);

  const onFilterChange = (next: DraftFilters) => {
    setDraft(next);
    setCursors([undefined]); // any filter change resets to page 1
  };

  const { data, isPending, isError, error, refetch, isPlaceholderData } = useCustomers(filters);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const canPrev = cursors.length > 1;
  const canNext = !!data?.next_cursor;

  // Stable so the memoized rows don't re-render on every parent state change.
  const onSelect = useCallback(
    (id: string) => navigate(`/customers/${id}`),
    [navigate],
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl">Customer Triage</h1>
          <p className="mt-1 font-mono text-xs text-muted">
            Scan the base for churn risk and high-value accounts. Click any row to open the flight
            deck.
          </p>
        </div>
        {data && (
          <div className="text-right">
            <div className="readout text-2xl text-green text-glow-green">
              {data.total.toLocaleString()}
            </div>
            <div className="placard">accounts in scope</div>
          </div>
        )}
      </header>

      <FilterBar value={draft} onChange={onFilterChange} />

      <div className="bezel overflow-hidden">
        {/* header row */}
        <div className="grid grid-cols-[7rem_1fr_9rem_7rem_1fr] items-center gap-4 border-b border-bezel px-4 py-3">
          {["ID", "Account", "Segment", "Churn", "Lifetime value"].map((h) => (
            <span key={h} className="placard">
              {h}
            </span>
          ))}
        </div>

        {isPending ? (
          <TableSkeleton rows={10} />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} onRetry={() => refetch()} />
        ) : data.items.length === 0 ? (
          <EmptyState
            title="No accounts match"
            hint="No customers fall inside these filters. Widen the churn ceiling or clear the segment."
          />
        ) : (
          <ul className={cn("divide-y divide-bezel/60", isPlaceholderData && "opacity-60")}>
            {data.items.map((c) => (
              <CustomerRow key={c.customer_id} c={c} onSelect={onSelect} />
            ))}
          </ul>
        )}
      </div>

      {/* pager */}
      {data && data.items.length > 0 && (
        <div className="flex items-center justify-between">
          <span className="placard">
            Page {pageNum} / {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={!canPrev}
              onClick={() => setCursors((c) => c.slice(0, -1))}
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={2} />
              Prev
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!canNext}
              onClick={() => data.next_cursor && setCursors((c) => [...c, data.next_cursor!])}
            >
              Next
              <ChevronRight className="h-4 w-4" strokeWidth={2} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Memoized so paging/filtering only re-renders rows whose data actually
// changed; the stable customer_id key keeps reconciliation cheap.
const CustomerRow = memo(function CustomerRow({
  c,
  onSelect,
}: {
  c: CustomerSummary;
  onSelect: (id: string) => void;
}) {
  const name = [c.first_name, c.last_name].filter(Boolean).join(" ") || "—";
  const band = churnBand(c.churn_score);
  return (
    <li>
      <button
        onClick={() => onSelect(c.customer_id)}
        className={cn(
          "grid w-full grid-cols-[7rem_1fr_9rem_7rem_1fr] items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-green/5",
          band === "alert" && "border-l-2 border-l-alert/70",
          band === "watch" && "border-l-2 border-l-amber/60",
          band === "ok" && "border-l-2 border-l-transparent",
        )}
      >
        <span className="readout text-xs text-muted">{c.customer_id}</span>
        <span className="min-w-0">
          <span className="block truncate font-display text-sm uppercase tracking-wide text-lum">
            {name}
          </span>
          <span className="block truncate font-mono text-xs text-muted">{c.email ?? "—"}</span>
        </span>
        <span className="font-display text-xs uppercase tracking-[0.1em] text-lum/80">
          {segmentName(c.segment_id)}
        </span>
        <ChurnReadout score={c.churn_score} />
        <span className="flex items-center gap-3">
          <span className="readout w-20 text-sm">{usd(c.lifetime_value)}</span>
          <span className="flex-1">
            <Meter frac={(c.lifetime_value ?? 0) / LTV_CEILING} />
          </span>
        </span>
      </button>
    </li>
  );
});
