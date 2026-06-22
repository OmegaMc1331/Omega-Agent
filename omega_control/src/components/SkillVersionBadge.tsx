export function SkillVersionBadge({ version }: { version: string }) {
  return <span className="inline-flex h-6 items-center rounded-full border border-white/10 bg-white/[0.04] px-2 text-[11px] text-zinc-400">v{version}</span>;
}
