import { X } from "lucide-react";

import { SEGMENTS, SEGMENT_IDS } from "@/lib/segments";
import { cn } from "@/lib/utils";

export interface DraftFilters {
  segment: string;
  minLtv: string;
  maxChurn: string;
}

export const EMPTY_FILTERS: DraftFilters = { segment: "", minLtv: "", maxChurn: "" };

/** Instrument-panel filter row: segment select + two numeric inputs. */
export function FilterBar({
  value,
  onChange,
}: {
  value: DraftFilters;
  onChange: (next: DraftFilters) => void;
}) {
  const set = (patch: Partial<DraftFilters>) => onChange({ ...value, ...patch });
  const dirty = value.segment || value.minLtv || value.maxChurn;

  return (
    <div className="bezel flex flex-wrap items-end gap-4 p-4">
      <Field label="Segment">
        <select
          value={value.segment}
          onChange={(e) => set({ segment: e.target.value })}
          className={inputCls}
        >
          <option value="">All segments</option>
          {SEGMENT_IDS.map((id) => (
            <option key={id} value={id}>
              {id} · {SEGMENTS[id]}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Min LTV ($)">
        <input
          type="number"
          inputMode="numeric"
          min={0}
          placeholder="0"
          value={value.minLtv}
          onChange={(e) => set({ minLtv: e.target.value })}
          className={cn(inputCls, "w-32")}
        />
      </Field>

      <Field label="Max churn (0–1)">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={1}
          step={0.05}
          placeholder="1.00"
          value={value.maxChurn}
          onChange={(e) => set({ maxChurn: e.target.value })}
          className={cn(inputCls, "w-32")}
        />
      </Field>

      {dirty && (
        <button
          onClick={() => onChange(EMPTY_FILTERS)}
          className="mb-0.5 inline-flex items-center gap-1.5 rounded-sm border border-bezel px-3 py-2 font-display text-xs uppercase tracking-[0.14em] text-muted transition-colors hover:border-alert/50 hover:text-alert"
        >
          <X className="h-3.5 w-3.5" strokeWidth={2} />
          Clear
        </button>
      )}
    </div>
  );
}

const inputCls =
  "h-10 rounded-sm border border-bezel bg-panel px-3 font-mono text-sm text-lum placeholder:text-muted/60 focus:border-green/60 focus:outline-none focus:ring-1 focus:ring-green/40";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="placard">{label}</span>
      {children}
    </label>
  );
}
