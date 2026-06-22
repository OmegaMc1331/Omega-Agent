import { useEffect, useState } from 'react';
import { ArrowLeft, Play, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { PromoteToLiveButton } from '../components/PromoteToLiveButton';
import { ShadowDiffViewer } from '../components/ShadowDiffViewer';
import { ShadowLiveComparison } from '../components/ShadowLiveComparison';
import { ShadowPlanCard } from '../components/ShadowPlanCard';
import { ShadowRiskReport } from '../components/ShadowRiskReport';
import type { ShadowRunView } from '../types/shadow';

export function ShadowRunDetailsPage({ shadowRunId, onBack }: { shadowRunId: string; onBack: () => void }) {
  const [item, setItem] = useState<ShadowRunView | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function load() {
    if (!shadowRunId) return;
    setItem(await api<ShadowRunView>(`/api/shadow/${shadowRunId}`));
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [shadowRunId]);

  async function execute(path: string, body: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      await api(`/api/shadow/${shadowRunId}/${path}`, { method: 'POST', body: JSON.stringify(body) });
      setMessage(`${path} terminé.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  if (!item) return <div className="p-6 text-sm text-zinc-500">Chargement du shadow run…</div>;
  const canPromote = item.status === 'succeeded';
  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <button onClick={onBack} className="secondary-button"><ArrowLeft size={15} /></button>
          <div>
            <div className="font-semibold text-stone-100">{item.objective}</div>
            <div className="mt-1 text-xs text-zinc-500">{item.id} · {item.status}</div>
          </div>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={15} /> Refresh</button>
      </div>
      {message && <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-4 py-3 text-sm text-zinc-300">{message}</div>}
      <div className="flex flex-wrap gap-2">
        {item.status === 'pending' && <button disabled={busy} onClick={() => execute('run')} className="primary-button"><Play size={15} /> Run shadow</button>}
        <PromoteToLiveButton
          disabled={busy || !canPromote}
          requiresApproval={item.risk_report?.recommendation === 'require_approval'}
          onPromote={() => execute('promote', { approved_by: 'omega-control-user' })}
          onReject={() => execute('reject')}
        />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <ShadowPlanCard steps={item.plan?.steps} />
        <ShadowRiskReport report={item.risk_report} />
      </div>
      <ShadowDiffViewer diff={item.predicted_diff} />
      <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
        <div className="mb-3 font-semibold text-stone-100">Shadow steps</div>
        <div className="space-y-2">
          {(item.steps || []).map((step, index) => (
            <div key={String(step.id || index)} className="flex items-center justify-between rounded-xl bg-white/[0.035] px-3 py-2 text-sm">
              <span className="text-zinc-300">{String(step.name || `Step ${index + 1}`)}</span>
              <span className="text-xs text-zinc-500">{String(step.status || '')}</span>
            </div>
          ))}
        </div>
      </section>
      <ShadowLiveComparison comparison={item.comparison} />
    </div>
  );
}
