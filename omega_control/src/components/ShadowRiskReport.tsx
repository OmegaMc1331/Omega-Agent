import { ShieldAlert } from 'lucide-react';
import type { ShadowRiskReport as ShadowRiskReportView } from '../types/shadow';

export function ShadowRiskReport({ report }: { report?: ShadowRiskReportView | null }) {
  if (!report) return <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4 text-sm text-zinc-500">Risk report non calculé.</section>;
  const tone = report.recommendation === 'reject' ? 'border-red-400/20 bg-red-500/10 text-red-100' : report.recommendation === 'require_approval' ? 'border-amber-400/20 bg-amber-500/10 text-amber-100' : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100';
  return (
    <section className="rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4">
      <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><ShieldAlert size={17} className="text-amber-300" /> Risk report</div>
      <div className={`mb-4 rounded-2xl border p-3 text-sm ${tone}`}>{report.recommendation} · risque {report.risk_level} · confiance {Math.round(report.confidence * 100)}%</div>
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <Metric label="Fichiers modifiés" value={report.files_modified} />
        <Metric label="Fichiers supprimés" value={report.files_deleted} />
        <Metric label="Commandes shell" value={report.shell_commands} />
        <Metric label="Appels externes" value={report.external_calls} />
        <Metric label="Policy denials" value={report.policy_denials} />
        <Metric label="Rollback" value={report.rollback_available ? 'disponible' : 'indisponible'} />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="flex justify-between rounded-xl bg-white/[0.035] px-3 py-2 text-zinc-400"><span>{label}</span><span className="text-stone-200">{value}</span></div>;
}
