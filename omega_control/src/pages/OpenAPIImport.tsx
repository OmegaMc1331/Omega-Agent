import { useState } from 'react';
import { FileText, Upload } from 'lucide-react';
import { api } from '../api/client';
import { type ConnectorView } from '../components/ConnectorCard';

export function OpenAPIImportPage() {
  const [path, setPath] = useState('');
  const [documentText, setDocumentText] = useState('');
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [trustLevel, setTrustLevel] = useState('local');
  const [result, setResult] = useState<ConnectorView | null>(null);
  const [error, setError] = useState('');

  async function submit() {
    setError('');
    setResult(null);
    let document: unknown = undefined;
    if (documentText.trim()) {
      try {
        document = JSON.parse(documentText);
      } catch (reason) {
        setError(`Invalid JSON: ${String(reason)}`);
        return;
      }
    }
    try {
      const connector = await api<ConnectorView>('/api/connectors/openapi/import', {
        method: 'POST',
        body: JSON.stringify({
          path: path || undefined,
          document,
          name: name || undefined,
          base_url: baseUrl || undefined,
          trust_level: trustLevel,
        }),
      });
      setResult(connector);
    } catch (reason) {
      setError(String(reason instanceof Error ? reason.message : reason));
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-6 max-sm:p-4">
      <div>
        <div className="flex items-center gap-2 font-semibold text-stone-100"><FileText size={18} className="text-zinc-400" /> OpenAPI Import</div>
        <p className="mt-1 text-sm text-zinc-500">Import a JSON OpenAPI manifest as a disabled connector. Enable it after policy review.</p>
      </div>
      <section className="grid gap-4 rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <label className="grid gap-1 text-sm text-zinc-400">
          Workspace path
          <input value={path} onChange={(event) => setPath(event.target.value)} className="field" placeholder="openapi.json" />
        </label>
        <label className="grid gap-1 text-sm text-zinc-400">
          Inline JSON
          <textarea value={documentText} onChange={(event) => setDocumentText(event.target.value)} className="field min-h-48" placeholder='{"openapi":"3.0.0","info":{"title":"Local API"},"paths":{}}' />
        </label>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="grid gap-1 text-sm text-zinc-400">
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} className="field" />
          </label>
          <label className="grid gap-1 text-sm text-zinc-400">
            Base URL
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="field" placeholder="http://127.0.0.1:8000" />
          </label>
          <label className="grid gap-1 text-sm text-zinc-400">
            Trust level
            <select value={trustLevel} onChange={(event) => setTrustLevel(event.target.value)} className="field">
              <option value="local">local</option>
              <option value="untrusted">untrusted</option>
              <option value="blocked">blocked</option>
            </select>
          </label>
        </div>
        <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          External execution is disabled in v1 unless a connector is explicitly enabled and policy allows the operation.
        </div>
        <button onClick={submit} className="primary-button w-fit"><Upload size={16} /> Import OpenAPI</button>
      </section>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      {result && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="font-medium text-stone-100">{result.name}</div>
          <div className="mt-1 text-sm text-zinc-500">{result.id}</div>
          <div className="mt-3 text-sm text-zinc-400">Status: {result.status}. Operations: {result.operations_count ?? result.operations?.length ?? 0}.</div>
        </section>
      )}
    </div>
  );
}
