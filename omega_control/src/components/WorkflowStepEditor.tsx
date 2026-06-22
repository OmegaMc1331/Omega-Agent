export function WorkflowStepEditor({ definition, onChange }: { definition: string; onChange: (value: string) => void }) {
  return (
    <textarea
      value={definition}
      onChange={(event) => onChange(event.target.value)}
      className="min-h-[420px] w-full resize-y rounded-2xl border border-white/10 bg-black/20 p-4 font-mono text-xs leading-5 text-zinc-200 outline-none transition focus:border-blue-400/30"
      spellCheck={false}
    />
  );
}
