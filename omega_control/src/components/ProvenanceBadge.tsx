type Provenance = {
  source_type?: string;
  source_id?: string | null;
  source_label?: string | null;
};

export function ProvenanceBadge({ provenance }: { provenance?: Provenance[] }) {
  const source = provenance?.[0];
  const label = source?.source_label || source?.source_type || 'unknown';
  return (
    <span className="inline-flex max-w-full items-center rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-xs text-zinc-400">
      <span className="truncate">source: {label}</span>
    </span>
  );
}
