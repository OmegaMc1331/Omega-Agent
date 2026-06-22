import { useEffect, useState } from 'react';
import { Code2, GitCommit, Play, RefreshCw, Search } from 'lucide-react';
import { api } from '../api/client';
import { DiffViewer, type DiffSummaryView } from '../components/DiffViewer';
import { PatchPlanCard, type PatchPlanView } from '../components/PatchPlanCard';
import { RepoSummaryCard, type RepoSummaryView } from '../components/RepoSummaryCard';
import { SelfHealingPanel } from '../components/SelfHealingPanel';
import { TestResultPanel, type TestRunView } from '../components/TestResultPanel';

type CodeTestResponse = TestRunView & {
  classified_error?: { error_type: string; title: string; summary: string; confidence: number };
  recovery?: { kind: string; message: string; safe_to_auto_apply?: boolean };
};

export function CodeWorkspacePage() {
  const [repo, setRepo] = useState<RepoSummaryView | null>(null);
  const [testRun, setTestRun] = useState<CodeTestResponse | null>(null);
  const [diff, setDiff] = useState<DiffSummaryView | null>(null);
  const [plans, setPlans] = useState<PatchPlanView[]>([]);
  const [command, setCommand] = useState('');
  const [commitMessage, setCommitMessage] = useState('Omega code workspace update');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const [nextRepo, nextPlans, nextDiff] = await Promise.all([
        api<RepoSummaryView>('/api/code/repo'),
        api<PatchPlanView[]>('/api/code/patch-plans'),
        api<DiffSummaryView>('/api/code/diff'),
      ]);
      setRepo(nextRepo);
      setPlans(nextPlans);
      setDiff(nextDiff);
      setError('');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function scan() {
    setRepo(await api<RepoSummaryView>('/api/code/scan', { method: 'POST', body: '{}' }));
  }

  async function runTests() {
    const payload = command.trim() ? { command: command.trim() } : {};
    const result = await api<CodeTestResponse>('/api/code/tests/run', { method: 'POST', body: JSON.stringify(payload) });
    setTestRun(result);
    await load();
  }

  async function createPatchPlan() {
    const problem = testRun?.summary || 'Plan de correction manuel';
    const plan = await api<PatchPlanView>('/api/code/patch-plans', { method: 'POST', body: JSON.stringify({ problem, proposed_changes: [] }) });
    setPlans((current) => [plan, ...current]);
  }

  async function applyPlan(plan: PatchPlanView) {
    const updated = await api<PatchPlanView>(`/api/code/patch-plans/${plan.id}/apply`, { method: 'POST', body: '{}' });
    setPlans((current) => current.map((item) => item.id === updated.id ? updated : item));
    setDiff(await api<DiffSummaryView>('/api/code/diff'));
  }

  async function verifyPlan(plan: PatchPlanView) {
    const updated = await api<PatchPlanView>(`/api/code/patch-plans/${plan.id}/verify`, { method: 'POST', body: '{}' });
    setPlans((current) => current.map((item) => item.id === updated.id ? updated : item));
  }

  async function commit() {
    await api<{ ok: boolean; output: string }>('/api/code/git/commit', { method: 'POST', body: JSON.stringify({ message: commitMessage, add_all: true }) });
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Code2 size={18} className="text-zinc-400" /> Code Workspace</div>
          <p className="mt-1 text-sm text-zinc-500">Analyse repo, tests, diff, patch plans et commit local dans le workspace.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={scan} className="secondary-button"><Search size={16} /> Scan repo</button>
          <button onClick={load} className="secondary-button"><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>}

      <RepoSummaryCard repo={repo} />

      <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div className="mb-3 text-sm font-semibold text-stone-100">Run tests</div>
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <input value={command} onChange={(event) => setCommand(event.target.value)} className="field" placeholder={repo?.test_commands?.[0] || 'Detected command'} />
          <button onClick={runTests} className="primary-button"><Play size={16} /> Run tests</button>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <TestResultPanel run={testRun} />
          <DiffViewer diff={diff} />
        </div>
        <div className="space-y-5">
          <SelfHealingPanel classified={testRun?.classified_error} suggestion={testRun?.recovery} />
          <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 text-sm font-semibold text-stone-100">Commit local</div>
            <input value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} className="field" />
            <button onClick={commit} className="secondary-button mt-3 w-full justify-center"><GitCommit size={16} /> Commit changes</button>
            <p className="mt-2 text-xs text-zinc-600">Aucun git push automatique.</p>
          </section>
        </div>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-stone-100">Patch plans</div>
          <button onClick={createPatchPlan} className="secondary-button h-9 px-3 text-xs">Create patch plan</button>
        </div>
        {plans.map((plan) => <PatchPlanCard key={plan.id} plan={plan} onApply={applyPlan} onVerify={verifyPlan} />)}
        {plans.length === 0 && <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-sm text-zinc-500">Aucun patch plan.</div>}
      </section>
    </div>
  );
}
