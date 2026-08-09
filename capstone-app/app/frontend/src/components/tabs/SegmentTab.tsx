import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { Button, Panel, PanelHeader } from "@/components/ui";
import { useOverrideSegment } from "@/lib/queries";
import { SEGMENTS, SEGMENT_IDS } from "@/lib/segments";

export function SegmentTab({ id, current }: { id: string; current: string | null }) {
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const toast = useToast();
  const override = useOverrideSegment(id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!target) return;
    try {
      await override.mutateAsync({ override_segment: target, reason: reason.trim() || undefined });
      toast("ok", "Segment override staged");
    } catch (err) {
      toast("err", (err as Error).message || "Override failed");
    }
  };

  return (
    <Panel className="max-w-2xl">
      <PanelHeader>
        <span className="placard">Override segment</span>
      </PanelHeader>
      <div className="p-5">
        <div className="mb-6 flex items-center gap-4">
          <div className="flex flex-col gap-1">
            <span className="placard">Current</span>
            <span className="font-display text-lg uppercase tracking-[0.1em] text-lum">
              {current ? `${current} · ${SEGMENTS[current] ?? current}` : "—"}
            </span>
          </div>
          <ArrowRight className="mt-4 h-5 w-5 text-muted" strokeWidth={1.75} />
          <div className="flex flex-col gap-1">
            <span className="placard">New</span>
            <span className="font-display text-lg uppercase tracking-[0.1em] text-green text-glow-green">
              {target ? `${target} · ${SEGMENTS[target]}` : "select…"}
            </span>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="flex flex-col gap-1.5">
            <span className="placard">Target segment</span>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="h-10 rounded-sm border border-bezel bg-panel px-3 font-mono text-sm text-lum focus:border-green/60 focus:outline-none focus:ring-1 focus:ring-green/40"
            >
              <option value="">Select a segment…</option>
              {SEGMENT_IDS.map((s) => (
                <option key={s} value={s}>
                  {s} · {SEGMENTS[s]}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="placard">Reason (optional)</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this override warranted?"
              className="h-10 rounded-sm border border-bezel bg-panel px-3 font-mono text-sm text-lum placeholder:text-muted/60 focus:border-green/60 focus:outline-none focus:ring-1 focus:ring-green/40"
            />
          </label>

          <div className="flex items-center justify-between">
            <span className="placard">upsert · re-submitting the same value is a no-op</span>
            <Button type="submit" disabled={!target || override.isPending}>
              {override.isPending ? "Staging…" : "Stage override"}
            </Button>
          </div>
        </form>
      </div>
    </Panel>
  );
}
