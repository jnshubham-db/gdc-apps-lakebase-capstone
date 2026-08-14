import { EmptyState } from "@/components/states";
import { Panel } from "@/components/ui";
import type { Transaction } from "@/lib/types";
import { cn, fmtDate, usd } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  completed: "text-green",
  pending: "text-amber",
  cancelled: "text-alert",
};

export function ActivityTab({ transactions }: { transactions: Transaction[] }) {
  if (transactions.length === 0) {
    return (
      <Panel>
        <EmptyState title="No activity" hint="This customer has no transactions on record yet." />
      </Panel>
    );
  }

  return (
    <Panel className="overflow-hidden">
      <div className="grid grid-cols-[8rem_1fr_7rem_8rem] gap-4 border-b border-bezel px-4 py-3">
        {["Date", "Transaction", "Channel", "Amount"].map((h) => (
          <span key={h} className="placard">
            {h}
          </span>
        ))}
      </div>
      <ul className="divide-y divide-bezel/60">
        {transactions.map((t) => (
          <li
            key={t.transaction_id}
            className="grid grid-cols-[8rem_1fr_7rem_8rem] items-center gap-4 px-4 py-3"
          >
            <span className="readout text-xs text-muted">{fmtDate(t.transaction_date)}</span>
            <span className="min-w-0">
              <span className="block truncate font-mono text-xs text-lum/90">
                {t.transaction_id}
              </span>
              <span
                className={cn(
                  "font-display text-[11px] uppercase tracking-[0.14em]",
                  STATUS_TONE[t.status ?? ""] ?? "text-muted",
                )}
              >
                {t.status ?? "—"}
              </span>
            </span>
            <span className="font-display text-xs uppercase tracking-[0.1em] text-lum/70">
              {t.channel ?? "—"}
            </span>
            <span className="readout text-sm">{usd(t.amount)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
