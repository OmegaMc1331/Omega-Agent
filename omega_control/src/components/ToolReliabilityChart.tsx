export type ToolReliabilityView = {
  tool_name: string;
  calls: number;
  failures: number;
  denials: number;
  success_rate: number;
};

export function ToolReliabilityChart({ tools }: { tools: ToolReliabilityView[] }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 text-sm font-semibold text-stone-100">Tool reliability</div>
      <div className="space-y-3">
        {tools.map((tool) => {
          const pct = Math.max(0, Math.min(100, Math.round((tool.success_rate || 0) * 100)));
          return (
            <div key={tool.tool_name}>
              <div className="mb-1 flex justify-between gap-3 text-sm">
                <span className="text-zinc-300">{tool.tool_name}</span>
                <span className="text-zinc-500">{pct}% · {tool.calls} calls</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full rounded-full bg-emerald-400/60" style={{ width: `${pct}%` }} />
              </div>
              {(tool.failures > 0 || tool.denials > 0) && <div className="mt-1 text-xs text-zinc-600">{tool.failures} failures · {tool.denials} denials</div>}
            </div>
          );
        })}
        {tools.length === 0 && <div className="text-sm text-zinc-500">Aucun tool journalisé.</div>}
      </div>
    </section>
  );
}
