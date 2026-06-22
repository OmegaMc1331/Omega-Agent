import { FileText } from 'lucide-react';

export function ResearchReportViewer({ report }: { report?: string | null }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-100"><FileText size={16} className="text-zinc-400" /> Rapport Markdown</div>
      {report
        ? <pre className="max-h-[680px] overflow-auto whitespace-pre-wrap rounded-xl bg-black/20 p-4 text-xs leading-6 text-zinc-300">{report}</pre>
        : <div className="text-sm text-zinc-500">Rapport indisponible.</div>}
    </section>
  );
}
