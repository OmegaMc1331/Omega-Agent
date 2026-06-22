export type PatchPlanView = {
  id: string;
  title: string;
  problem: string;
  proposed_changes: Array<Record<string, unknown>>;
  files_to_modify: string[];
  risk_level: string;
  status: string;
  updated_at: string;
};

export function PatchPlanCard({
  plan,
  onApply,
  onVerify,
}: {
  plan: PatchPlanView;
  onApply: (plan: PatchPlanView) => void;
  onVerify: (plan: PatchPlanView) => void;
}) {
  return (
    <article className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{plan.status}</span>
            <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{plan.risk_level}</span>
          </div>
          <h3 className="mt-3 text-sm font-semibold text-stone-100">{plan.title}</h3>
        </div>
        <div className="flex gap-2">
          <button onClick={() => onApply(plan)} className="secondary-button h-9 px-3 text-xs">Apply</button>
          <button onClick={() => onVerify(plan)} className="secondary-button h-9 px-3 text-xs">Verify</button>
        </div>
      </div>
      <p className="mt-3 text-sm text-zinc-300">{plan.problem}</p>
      {plan.files_to_modify.length > 0 && <div className="mt-3 text-xs text-zinc-500">Files: {plan.files_to_modify.join(', ')}</div>}
    </article>
  );
}
