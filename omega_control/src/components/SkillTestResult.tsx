import { CheckCircle2, XCircle } from 'lucide-react';
import type { SkillTestRunView } from '../types/skills';

export function SkillTestResult({ test }: { test: SkillTestRunView }) {
  const passed = test.status === 'passed';
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-3">
      <div className="flex items-center justify-between gap-3">
        <span className={`flex items-center gap-2 text-sm ${passed ? 'text-emerald-200' : 'text-red-200'}`}>
          {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />} {test.status}
        </span>
        <span className="text-xs text-zinc-600">v{test.version} · {new Date(test.created_at).toLocaleString('fr-FR')}</span>
      </div>
    </div>
  );
}
