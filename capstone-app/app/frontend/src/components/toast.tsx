import { CheckCircle2, XCircle } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

type Toast = { id: number; kind: "ok" | "err"; msg: string };
const ToastCtx = React.createContext<(kind: Toast["kind"], msg: string) => void>(() => {});

export function useToast() {
  return React.useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const push = React.useCallback((kind: Toast["kind"], msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-center gap-2.5 rounded-sm border px-4 py-2.5 font-display text-sm uppercase tracking-[0.12em] shadow-bezel animate-[toast_.2s_ease-out]",
              t.kind === "ok"
                ? "border-green/50 bg-face text-green shadow-glow"
                : "border-alert/50 bg-face text-alert shadow-glow-alert",
            )}
          >
            {t.kind === "ok" ? (
              <CheckCircle2 className="h-4 w-4" strokeWidth={2} />
            ) : (
              <XCircle className="h-4 w-4" strokeWidth={2} />
            )}
            {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
