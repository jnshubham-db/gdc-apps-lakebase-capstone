import { ExternalLink, Maximize2, Minimize2, Radio, RotateCcw, Send, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { useConfig } from "@/lib/queries";
import type { GenieMessageOut, GenieResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"]);
const POLL_MS = 1200;
const CAP_MS = 30_000;

type Turn =
  | { role: "user"; text: string }
  | { role: "genie"; pending: boolean; text?: string; result?: GenieResult | null; error?: string };

function ResultTable({ result }: { result: GenieResult }) {
  const rows = result.rows.slice(0, 10);
  return (
    <div className="mt-2 overflow-x-auto rounded-sm border border-bezel">
      <table className="w-full border-collapse font-mono text-[11px]">
        <thead>
          <tr>
            {result.columns.map((c) => (
              <th key={c} className="border-b border-bezel bg-face px-2 py-1 text-left text-muted">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {(r as unknown[]).map((cell, j) => (
                <td key={j} className="border-b border-bezel/50 px-2 py-1 text-lum/90">
                  {cell === null ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GenieWidget() {
  const cfg = useConfig();
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [cid, setCid] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const workspaceUrl =
    cfg.data?.databricks_host && cfg.data?.genie_space_id
      ? `${cfg.data.databricks_host}/genie/rooms/${cfg.data.genie_space_id}`
      : null;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const poll = useCallback(async (conv: string, mid: string) => {
    const deadline = Date.now() + CAP_MS;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      let msg: GenieMessageOut;
      try {
        msg = await api.genie.getMessage(conv, mid);
      } catch (e) {
        return { status: "FAILED", text: null, result: null, error: String(e) } as GenieMessageOut;
      }
      if (TERMINAL.has(msg.status)) return msg;
      if (Date.now() > deadline) return { ...msg, status: "TIMEOUT" };
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
  }, []);

  async function send() {
    const content = input.trim();
    if (!content || busy) return;
    setInput("");
    setBusy(true);
    setTurns((t) => [...t, { role: "user", text: content }, { role: "genie", pending: true }]);

    try {
      let conv = cid;
      let mid: string;
      if (conv) {
        mid = (await api.genie.followUp(conv, content)).message_id;
      } else {
        const started = await api.genie.start(content);
        conv = started.conversation_id;
        mid = started.message_id;
        setCid(conv);
      }
      const msg = await poll(conv, mid);
      setTurns((t) => {
        const next = [...t];
        const err =
          msg.status === "TIMEOUT"
            ? "Genie is taking too long — try again."
            : msg.status === "FAILED" || msg.error
              ? msg.error || "Genie couldn't answer that."
              : undefined;
        next[next.length - 1] = {
          role: "genie",
          pending: false,
          text: err ? undefined : msg.text ?? undefined,
          result: err ? undefined : msg.result,
          error: err,
        };
        return next;
      });
    } catch (e) {
      setTurns((t) => {
        const next = [...t];
        next[next.length - 1] = { role: "genie", pending: false, error: String(e) };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setCid(null);
    setTurns([]);
    setInput("");
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 inline-flex items-center gap-2 rounded-full border border-green/60 bg-green/10 px-4 py-3 font-display text-sm uppercase tracking-[0.14em] text-green shadow-glow transition-all hover:bg-green hover:text-panel"
      >
        <Radio className="h-4 w-4" strokeWidth={2} />
        Ask Genie
      </button>
    );
  }

  return (
    <div
      className={cn(
        "fixed bottom-6 right-6 z-50 flex flex-col rounded-sm border border-bezel bg-panel shadow-bezel",
        wide ? "h-[80vh] w-[560px]" : "h-[520px] w-[380px]",
      )}
    >
      <div className="flex items-center justify-between border-b border-bezel px-3 py-2">
        <span className="inline-flex items-center gap-2 font-display text-sm uppercase tracking-[0.14em] text-lum">
          <Radio className="h-4 w-4 text-green" strokeWidth={2} />
          Genie
        </span>
        <div className="flex items-center gap-1">
          {wide && workspaceUrl && (
            <a
              href={workspaceUrl}
              target="_blank"
              rel="noreferrer"
              className="mr-1 inline-flex items-center gap-1 font-mono text-[11px] text-muted hover:text-lum"
            >
              <ExternalLink className="h-3.5 w-3.5" /> workspace
            </a>
          )}
          <Button variant="ghost" size="icon" onClick={reset} aria-label="New chat">
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setWide((w) => !w)} aria-label="Resize">
            {wide ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {turns.length === 0 && (
          <p className="mt-6 text-center font-mono text-xs text-muted">
            Ask about segments, LTV, churn, tickets…
          </p>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="ml-8 rounded-sm border border-green/30 bg-green/5 px-3 py-2 text-sm text-lum">
              {t.text}
            </div>
          ) : (
            <div key={i} className="mr-8">
              {t.pending ? (
                <div className="inline-flex items-center gap-1 font-mono text-xs text-muted">
                  <span className="animate-pulse">▍</span> Genie is thinking…
                </div>
              ) : t.error ? (
                <div className="rounded-sm border border-amber/60 bg-amber/10 px-3 py-2 text-sm text-amber">
                  {t.error}
                </div>
              ) : (
                <div className="rounded-sm border border-bezel bg-face px-3 py-2 text-sm text-lum/90">
                  {t.text && <p className="whitespace-pre-wrap">{t.text}</p>}
                  {t.result && t.result.columns.length > 0 && <ResultTable result={t.result} />}
                </div>
              )}
            </div>
          ),
        )}
      </div>

      <form
        className="flex items-center gap-2 border-t border-bezel px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Genie…"
          disabled={busy}
          className="flex-1 rounded-sm border border-bezel bg-panel px-2 py-1.5 font-mono text-sm text-lum placeholder:text-muted focus:border-green/50 focus:outline-none"
        />
        <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
