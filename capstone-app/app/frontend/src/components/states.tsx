import { AlertTriangle, type LucideIcon, RefreshCw, SearchX } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "./ui";

/** Shimmering panel block — instrument warming up. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-sm bg-bezel/70", className)} />;
}

/** Full-route fallback while a lazy page loads. */
export function RouteFallback() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

/** Table skeleton: header placard + N shimmering rows. */
export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="ml-auto h-4 w-24" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

/** No-signal empty state — deliberate, not blank. */
export function EmptyState({
  title,
  hint,
  icon: Icon = SearchX,
}: {
  title: string;
  hint?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-full border border-bezel bg-face">
        <Icon className="h-6 w-6 text-muted" strokeWidth={1.5} />
      </div>
      <div className="font-display text-lg uppercase tracking-[0.12em] text-lum">{title}</div>
      {hint && <p className="max-w-sm font-mono text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Recoverable error — a caution lamp, never a dead page. */
export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-full border border-alert/50 bg-alert/10 shadow-glow-alert">
        <AlertTriangle className="h-6 w-6 text-alert" strokeWidth={1.75} />
      </div>
      <div className="font-display text-lg uppercase tracking-[0.12em] text-alert text-glow-alert">
        Signal lost
      </div>
      <p className="max-w-sm font-mono text-xs text-muted">
        {message ?? "The instrument failed to read. Check the connection and re-try."}
      </p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-1">
          <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} />
          Re-try
        </Button>
      )}
    </div>
  );
}
