import { Send } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/states";
import { useToast } from "@/components/toast";
import { Button, Panel, PanelHeader } from "@/components/ui";
import { useAddNote } from "@/lib/queries";
import { fmtDate } from "@/lib/utils";

interface SessionNote {
  note_id: string;
  note_text: string;
  created_at: string;
}

export function NotesTab({ id }: { id: string }) {
  const [text, setText] = useState("");
  // Notes are write-only to Lakebase staging (no GET endpoint in T3); the
  // forward-ETL job (T7) merges them into gold. We surface notes added this
  // session so the write is immediately visible, per the T3 done-check.
  const [session, setSession] = useState<SessionNote[]>([]);
  const toast = useToast();
  const addNote = useAddNote(id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    try {
      const res = await addNote.mutateAsync(body);
      setSession((s) => [{ note_id: res.note_id, note_text: body, created_at: res.created_at }, ...s]);
      setText("");
      toast("ok", "Note logged & audited");
    } catch (err) {
      toast("err", (err as Error).message || "Write failed");
    }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
      <Panel className="h-fit">
        <PanelHeader>
          <span className="placard">Log a note</span>
        </PanelHeader>
        <form onSubmit={submit} className="space-y-4 p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            maxLength={2000}
            placeholder="Observation, follow-up, or context for this account…"
            className="w-full resize-none rounded-sm border border-bezel bg-panel p-3 font-mono text-sm text-lum placeholder:text-muted/60 focus:border-green/60 focus:outline-none focus:ring-1 focus:ring-green/40"
          />
          <div className="flex items-center justify-between">
            <span className="placard">{text.length}/2000 · writes to staging + audit log</span>
            <Button type="submit" disabled={!text.trim() || addNote.isPending}>
              <Send className="h-4 w-4" strokeWidth={2} />
              {addNote.isPending ? "Logging…" : "Log note"}
            </Button>
          </div>
        </form>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader>
          <span className="placard">This session</span>
          <span className="placard">{session.length} logged</span>
        </PanelHeader>
        {session.length === 0 ? (
          <EmptyState
            title="No notes this session"
            hint="Notes you log appear here immediately. Prior notes live in Lakebase staging until the forward-ETL job merges them into gold (T7)."
          />
        ) : (
          <ul className="divide-y divide-bezel/60">
            {session.map((n) => (
              <li key={n.note_id} className="p-4">
                <p className="whitespace-pre-wrap font-mono text-sm text-lum/90">{n.note_text}</p>
                <div className="mt-2 flex items-center gap-3">
                  <span className="placard !text-[10px]">{fmtDate(n.created_at)}</span>
                  <span className="inline-flex items-center gap-1 rounded-sm border border-green/40 px-1.5 py-0.5 font-display text-[9px] uppercase tracking-[0.14em] text-green">
                    audited
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
