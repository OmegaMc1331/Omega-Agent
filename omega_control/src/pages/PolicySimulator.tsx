import { useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';
import { api } from '../api/client';
import { PolicySimulationResult, type PolicySimulationView } from '../components/PolicySimulationResult';

export function PolicySimulatorPage() {
  const [tool, setTool] = useState('write_file');
  const [path, setPath] = useState('test.txt');
  const [command, setCommand] = useState('');
  const [channel, setChannel] = useState('local');
  const [sourceTrust, setSourceTrust] = useState('local');
  const [fileCount, setFileCount] = useState(0);
  const [result, setResult] = useState<PolicySimulationView | null>(null);
  const [error, setError] = useState('');

  async function simulate() {
    setError('');
    try {
      const argumentsPayload: Record<string, unknown> = {};
      if (path) argumentsPayload.relative_path = path;
      if (command) argumentsPayload.command = command;
      if (fileCount) argumentsPayload.file_count = fileCount;
      setResult(await api<PolicySimulationView>('/api/policy/simulate', {
        method: 'POST',
        body: JSON.stringify({
          tool_name: tool,
          arguments: argumentsPayload,
          channel,
          source_trust: sourceTrust,
          file_count: fileCount,
        }),
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><FlaskConical size={18} className="text-zinc-400" /> Policy Simulator</div>
        <p className="mt-1 text-sm text-zinc-500">Simule une action avec le même moteur de policy utilisé par ToolBroker.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[420px_1fr]">
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="grid gap-3">
            <label className="space-y-1 text-xs text-zinc-500">
              Tool
              <input value={tool} onChange={(event) => setTool(event.target.value)} className="field" />
            </label>
            <label className="space-y-1 text-xs text-zinc-500">
              Path
              <input value={path} onChange={(event) => setPath(event.target.value)} className="field" />
            </label>
            <label className="space-y-1 text-xs text-zinc-500">
              Command
              <input value={command} onChange={(event) => setCommand(event.target.value)} className="field" placeholder="npm run build" />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs text-zinc-500">
                Channel
                <select value={channel} onChange={(event) => setChannel(event.target.value)} className="field">
                  {['local', 'mobile', 'webhook', 'telegram', 'discord'].map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <label className="space-y-1 text-xs text-zinc-500">
                Source trust
                <select value={sourceTrust} onChange={(event) => setSourceTrust(event.target.value)} className="field">
                  {['local', 'trusted', 'untrusted'].map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
            </div>
            <label className="space-y-1 text-xs text-zinc-500">
              File count
              <input type="number" value={fileCount} onChange={(event) => setFileCount(Number(event.target.value))} className="field" />
            </label>
            <button onClick={simulate} className="primary-button"><Play size={16} /> Simulate</button>
            {error && <div className="rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
          </div>
        </section>
        <PolicySimulationResult result={result} />
      </div>
    </div>
  );
}
