import { TerminalSquare } from 'lucide-react';

export type ActionView = {
  id: string;
  tool_name?: string | null;
  action_type: string;
  status: string;
  risk_level: string;
  rollback_available: boolean;
  arguments?: Record<string, unknown>;
  observation?: Record<string, unknown> | null;
};

export function ActionJournalPanel({ actions }: { actions: ActionView[] }) {
  if (actions.length === 0) return <div className="text-sm text-zinc-500">Aucune action journalisée.</div>;
  return (
    <div className="grid gap-2">
      {actions.map((action) => (
        <div key={action.id} className="rounded-2xl border border-white/10 bg-black/10 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><TerminalSquare size={15} className="text-zinc-400" /> {action.tool_name || action.action_type}</div>
            <div className="flex gap-2 text-[11px] text-zinc-400"><span>{action.status}</span><span>{action.risk_level}</span><span>rollback={String(action.rollback_available)}</span></div>
          </div>
          <pre className="mt-2 max-h-40 overflow-auto rounded-2xl border border-white/10 bg-black/20 p-2 text-[11px] text-zinc-400">{JSON.stringify(action.arguments || {}, null, 2)}</pre>
        </div>
      ))}
    </div>
  );
}
