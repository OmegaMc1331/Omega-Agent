import { useMemo, useState } from 'react';
import { Save } from 'lucide-react';
import { api } from '../api/client';
import { WorkflowStepEditor } from '../components/WorkflowStepEditor';
import type { WorkflowView } from '../components/WorkflowCard';

const sampleDefinition = {
  name: 'Manual Workflow',
  description: 'Workflow manuel cree depuis Omega Control.',
  version: '1.0',
  inputs: {},
  steps: [
    {
      id: 'scan',
      type: 'tool',
      name: 'Scan workspace',
      tool: 'list_tree',
      arguments: { relative_path: '.', max_entries: 100 },
      on_error: 'continue',
    },
    {
      id: 'summary',
      type: 'final',
      name: 'Summary',
      message: 'Workflow completed.',
    },
  ],
};

export function WorkflowEditorPage() {
  const [definition, setDefinition] = useState(JSON.stringify(sampleDefinition, null, 2));
  const [result, setResult] = useState('');
  const [error, setError] = useState('');

  const preview = useMemo(() => {
    try {
      const parsed = JSON.parse(definition);
      return Array.isArray(parsed.steps) ? parsed.steps : [];
    } catch {
      return [];
    }
  }, [definition]);

  async function save() {
    setError('');
    setResult('');
    try {
      const parsed = JSON.parse(definition);
      const workflow = await api<WorkflowView>('/api/workflows', { method: 'POST', body: JSON.stringify({ definition: parsed }) });
      setResult(`Workflow saved: ${workflow.id}`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">Workflow Editor</div>
          <p className="mt-1 text-sm text-zinc-500">Edition JSON simple avec validation backend.</p>
        </div>
        <button onClick={save} className="primary-button"><Save size={16} /> Save workflow</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>}
      {result && <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">{result}</div>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <WorkflowStepEditor definition={definition} onChange={setDefinition} />
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="mb-3 text-sm font-semibold text-stone-100">Preview steps</div>
          <div className="space-y-2">
            {preview.map((step: { id?: string; type?: string; name?: string }, index: number) => (
              <div key={`${step.id || index}`} className="rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm">
                <div className="text-stone-100">{index + 1}. {step.name || step.id || 'Step'}</div>
                <div className="mt-1 text-xs text-zinc-500">{step.id || '-'} · {step.type || '-'}</div>
              </div>
            ))}
            {preview.length === 0 && <div className="text-sm text-zinc-500">No valid steps to preview.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
