import { Gauge } from "@/components/Gauge";
import { ErrorState, Skeleton } from "@/components/states";
import { Panel, PanelHeader } from "@/components/ui";
import { useCustomerMetrics } from "@/lib/queries";
import { usd } from "@/lib/utils";

// Ceilings for gauge arc scaling (readouts show the true value).
const SPEND_CEILING = 120_000;
const WINDOW_CEILING = 20_000;
const TICKET_CEILING = 10;

export function MetricsTab({ id }: { id: string }) {
  const { data, isPending, isError, error, refetch } = useCustomerMetrics(id);

  if (isPending) {
    return (
      <Panel className="p-6">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex flex-col items-center gap-3">
              <Skeleton className="h-[148px] w-[148px] rounded-full" />
              <Skeleton className="h-3 w-20" />
            </div>
          ))}
        </div>
        <p className="placard mt-6 text-center">
          computing live from the warehouse — this instrument runs slower
        </p>
      </Panel>
    );
  }

  if (isError) {
    return (
      <Panel>
        <ErrorState
          message={
            (error as Error)?.message ??
            "The warehouse metrics query failed. Your OBO session may need re-authorization."
          }
          onRetry={() => refetch()}
        />
      </Panel>
    );
  }

  const csat = data.avg_csat;
  const csatTone = csat == null ? "green" : csat >= 4 ? "green" : csat >= 3 ? "amber" : "alert";
  const ticketTone =
    data.open_tickets === 0 ? "green" : data.open_tickets <= 3 ? "amber" : "alert";

  return (
    <div className="space-y-5">
      <Panel className="p-6">
        <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-4">
          <Gauge
            value={data.lifetime_spend / SPEND_CEILING}
            readout={compact(data.lifetime_spend)}
            sub="USD"
            label="Lifetime spend"
          />
          <Gauge
            value={data.spend_90d / WINDOW_CEILING}
            readout={compact(data.spend_90d)}
            sub="90-day"
            label="Recent spend"
            tone="amber"
          />
          <Gauge
            value={data.open_tickets / TICKET_CEILING}
            readout={String(data.open_tickets)}
            sub="open"
            label="Support tickets"
            tone={ticketTone}
          />
          <Gauge
            value={(csat ?? 0) / 5}
            readout={csat == null ? "—" : csat.toFixed(1)}
            sub="/ 5 CSAT"
            label="Satisfaction"
            tone={csatTone}
          />
        </div>
        <div className="mt-6 flex flex-wrap justify-center gap-x-8 gap-y-2 border-t border-bezel pt-4 font-mono text-xs text-muted">
          <span>30-day spend {usd(data.spend_30d)}</span>
          <span>Segment {data.segment_name ?? "—"}</span>
        </div>
      </Panel>

      <Panel>
        <PanelHeader>
          <span className="placard">Top categories · lifetime</span>
        </PanelHeader>
        <div className="p-4">
          {data.top_categories.length === 0 ? (
            <p className="py-6 text-center font-mono text-xs text-muted">
              No completed purchases yet.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.top_categories.map((c) => {
                const max = data.top_categories[0].amount || 1;
                return (
                  <li key={c.category} className="flex items-center gap-4">
                    <span className="w-40 truncate font-display text-xs uppercase tracking-[0.1em] text-lum/80">
                      {c.category}
                    </span>
                    <span className="flex-1">
                      <span
                        className="block h-2 rounded-sm"
                        style={{
                          width: `${Math.max(4, (c.amount / max) * 100)}%`,
                          background: "#39FF9A",
                          boxShadow: "0 0 6px rgba(57,255,154,0.4)",
                        }}
                      />
                    </span>
                    <span className="readout w-20 text-right text-xs">{usd(c.amount)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Panel>
    </div>
  );
}

/** Compact readout for a gauge center, e.g. 66750 → "66.8K". */
function compact(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(Math.round(n));
}
