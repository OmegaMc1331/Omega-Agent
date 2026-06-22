import { useEffect, useMemo, useState } from 'react';
import { ListChecks, RefreshCw, ScanSearch, Search } from 'lucide-react';
import { api } from '../api/client';
import { WorkflowCard, type WorkflowView } from '../components/WorkflowCard';
import { WorkflowTemplateCard, type WorkflowTemplateView } from '../components/WorkflowTemplateCard';

export function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowView[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplateView[]>([]);
  const [selected, setSelected] = useState<WorkflowView | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  async function load() {
    setLoading(true);
    try {
      const [nextWorkflows, nextTemplates] = await Promise.all([
        api<WorkflowView[]>('/api/workflows'),
        api<WorkflowTemplateView[]>('/api/workflows/templates'),
      ]);
      setWorkflows(nextWorkflows);
      setTemplates(nextTemplates);
      setSelected((current) => nextWorkflows.find((item) => item.id === current?.id) || nextWorkflows[0] || null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return workflows;
    return workflows.filter((workflow) => `${workflow.name} ${workflow.description}`.toLowerCase().includes(needle));
  }, [workflows, query]);

  async function createFromTemplate(template: WorkflowTemplateView) {
    const workflow = await api<WorkflowView>('/api/workflows', { method: 'POST', body: JSON.stringify({ definition: template.definition, metadata: { template_id: template.id } }) });
    setMessage(`Workflow created: ${workflow.name}`);
    await load();
  }

  async function runWorkflow(workflow: WorkflowView) {
    const run = await api<{ id: string; status: string }>(`/api/workflows/${workflow.id}/run`, { method: 'POST', body: JSON.stringify({ input: {} }) });
    setMessage(`Workflow run ${run.status}: ${run.id}`);
    await load();
  }

  async function runWorkflowShadow(workflow: WorkflowView) {
    const run = await api<{ id: string; status: string }>(`/api/workflows/${workflow.id}/shadow`, { method: 'POST', body: '{}' });
    setMessage(`Shadow run ${run.status}: ${run.id}`);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><ListChecks size={18} className="text-zinc-400" /> Workflows</div>
          <p className="mt-1 text-sm text-zinc-500">Workflows durables, pausables et observables via Omega Runtime.</p>
        </div>
        <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
      </div>
      {message && <div className="rounded-2xl border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">{message}</div>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-3">
          <label className="relative block">
            <Search size={15} className="pointer-events-none absolute left-3 top-3 text-zinc-500" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} className="field pl-9" placeholder="Search workflows" />
          </label>
          <div className="grid gap-3 md:grid-cols-2">
            {filtered.map((workflow) => (
              <WorkflowCard key={workflow.id} workflow={workflow} selected={selected?.id === workflow.id} onSelect={setSelected} onRun={runWorkflow} />
            ))}
          </div>
          {filtered.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">No workflow yet.</div>}
        </div>
        <div className="space-y-4">
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 text-sm font-semibold text-stone-100">Selected workflow</div>
            {selected ? (
              <>
                <pre className="max-h-80 overflow-auto rounded-xl bg-black/20 p-3 text-[11px] text-zinc-400">{JSON.stringify(selected.definition, null, 2)}</pre>
                <button onClick={() => runWorkflowShadow(selected)} className="secondary-button mt-3"><ScanSearch size={15} /> Run in Shadow</button>
              </>
            ) : (
              <div className="text-sm text-zinc-500">Select a workflow to inspect its definition.</div>
            )}
          </section>
          <section className="space-y-3">
            <div className="text-sm font-semibold text-stone-100">Templates</div>
            {templates.map((template) => <WorkflowTemplateCard key={template.id} template={template} onCreate={createFromTemplate} />)}
          </section>
        </div>
      </div>
    </div>
  );
}
