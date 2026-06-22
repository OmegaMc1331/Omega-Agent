type Tone = 'slate' | 'green' | 'amber' | 'red' | 'blue';

const tones: Record<Tone, string> = {
  slate: 'border-white/10 bg-white/[0.045] text-zinc-300',
  green: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100',
  amber: 'border-amber-400/20 bg-amber-400/10 text-amber-100',
  red: 'border-red-400/20 bg-red-500/10 text-red-100',
  blue: 'border-blue-400/20 bg-blue-500/10 text-blue-100',
};

export function RunStatusBadge({ status }: { status: string }) {
  const tone: Tone = status === 'succeeded' ? 'green' : status === 'failed' || status === 'cancelled' ? 'red' : status === 'running' ? 'blue' : status === 'needs_approval' || status === 'paused' ? 'amber' : 'slate';
  return <span className={`inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium ${tones[tone]}`}>{status}</span>;
}
