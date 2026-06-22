export function ScopeBadge({ scope }: { scope: string }) {
  return <span className="inline-flex h-6 items-center rounded-full border border-white/10 bg-white/[0.045] px-2 text-[11px] text-zinc-300">{scope}</span>;
}
