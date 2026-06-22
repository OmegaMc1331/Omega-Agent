export function ConnectorScopeEditor({ scopes }: { scopes?: string[] }) {
  const items = scopes || [];
  if (items.length === 0) return <span className="text-xs text-zinc-600">No scopes</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((scope) => (
        <span key={scope} className="rounded-full border border-white/10 bg-white/[0.045] px-2 py-0.5 text-xs text-zinc-400">
          {scope}
        </span>
      ))}
    </div>
  );
}
