import { ExternalLink, Play } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { useToast } from "@/components/toast";
import { Button, Panel, PanelHeader } from "@/components/ui";
import { useForwardEtlRun, useForwardEtlRuns, useRunForwardEtl } from "@/lib/queries";
import type { RunSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const TERMINAL = new Set(["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]);

function tone(state: string, result: string | null): "green" | "amber" | "alert" {
  if (!TERMINAL.has(state)) return "amber"; // running / pending
  if (result === "SUCCESS") return "green";
  return "alert";
}

const TONE_CLS: Record<string, string> = {
  green: "border-green/50 text-green bg-green/10",
  amber: "border-amber/60 text-amber bg-amber/10",
  alert: "border-alert/60 text-alert bg-alert/10",
};

function StatePill({ state, result }: { state: string; result: string | null }) {
  const t = tone(state, result);
  const label = TERMINAL.has(state) ? (result ?? state) : state;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider",
        TONE_CLS[t],
      )}
    >
      {label}
    </span>
  );
}

function fmtTime(ms: number | null): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

function fmtDuration(ms: number | null): string {
  if (!ms) return "—";
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function Reports() {
  const runs = useForwardEtlRuns();
  const trigger = useRunForwardEtl();
  const toast = useToast();
  const [activeRun, setActiveRun] = useState<number | null>(null);

  const inFlight = activeRun != null;
  const active = useForwardEtlRun(activeRun, inFlight);
  const activeSettled = active.data && TERMINAL.has(active.data.state);
  const busy = trigger.isPending || (inFlight && !activeSettled);

  async function onRun() {
    try {
      const { run_id } = await trigger.mutateAsync();
      setActiveRun(run_id);
      toast("ok", `Forward-ETL run ${run_id} started`);
    } catch (e) {
      toast("err", e instanceof Error ? e.message : "Failed to start run");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl uppercase tracking-[0.12em] text-lum">
            Forward ETL
          </h1>
          <p className="font-mono text-xs text-muted">
            Promote staging notes &amp; overrides → Delta gold
          </p>
        </div>
        <Button onClick={onRun} disabled={busy}>
          <Play className="h-4 w-4" strokeWidth={2} />
          {busy ? "Running…" : "Run forward-ETL"}
        </Button>
      </div>

      {active.data && (
        <Panel className="mb-4">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">
                Run {active.data.run_id}
              </span>
              <StatePill state={active.data.state} result={active.data.result_state} />
            </div>
            {active.data.run_page_url && (
              <a
                href={active.data.run_page_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-mono text-[11px] text-muted hover:text-lum"
              >
                <ExternalLink className="h-3.5 w-3.5" /> workspace
              </a>
            )}
          </div>
        </Panel>
      )}

      <Panel>
        <PanelHeader>
          <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">
            Recent runs
          </span>
        </PanelHeader>
        {runs.isLoading ? (
          <TableSkeleton rows={5} />
        ) : runs.isError ? (
          <ErrorState message="Could not load run history." onRetry={() => runs.refetch()} />
        ) : !runs.data || runs.data.length === 0 ? (
          <EmptyState title="No runs yet" hint="Trigger a forward-ETL run to see history." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr className="text-left text-muted">
                  <th className="px-4 py-2 font-normal">Run</th>
                  <th className="px-4 py-2 font-normal">State</th>
                  <th className="px-4 py-2 font-normal">Started</th>
                  <th className="px-4 py-2 font-normal">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r: RunSummary) => (
                  <tr key={r.run_id} className="border-t border-bezel/60 text-lum/90">
                    <td className="px-4 py-2">{r.run_id}</td>
                    <td className="px-4 py-2">
                      <StatePill state={r.state} result={r.result_state} />
                    </td>
                    <td className="px-4 py-2">{fmtTime(r.start_time)}</td>
                    <td className="px-4 py-2">{fmtDuration(r.duration_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
