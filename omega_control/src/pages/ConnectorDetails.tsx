import { useEffect, useState } from 'react';
import { Plug, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { type ConnectorView } from '../components/ConnectorCard';
import { ConnectorOperationTable, type ConnectorOperationView } from '../components/ConnectorOperationTable';
import { ConnectorScopeEditor } from '../components/ConnectorScopeEditor';

export function ConnectorDetailsPage() {
  const [items, setItems] = useState<ConnectorView[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [connector, setConnector] = useState<ConnectorView | null>(null);
  const [operations, setOperations] = useState<ConnectorOperationView[]>([]);
  const [error, setError] = useState('');

  async function load(nextId = selectedId) {
    const connectors = await api<ConnectorView[]>('/api/connectors');
    setItems(connectors);
    const id = nextId || connectors[0]?.id || '';
    setSelectedId(id);
    if (!id) return;
    const [detail, ops] = await Promise.all([
      api<ConnectorView>(`/api/connectors/${encodeURIComponent(id)}`),
      api<ConnectorOperationView[]>(`/api/connectors/${encodeURIComponent(id)}/operations`),
    ]);
    setConnector(detail);
    setOperations(ops);
  }

  useEffect(() => {
    load().catch((reason) => setError(String(reason.message || reason)));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Plug size={18} className="text-zinc-400" /> Connector details</div>
          <p className="mt-1 text-sm text-zinc-500">Inspect manifest, scopes, auth reference and operations.</p>
        </div>
        <button onClick={() => load().catch((reason) => setError(String(reason.message || reason)))} className="secondary-button"><RefreshCw size={16} /> Refresh</button>
      </div>
      {error && <div className="rounded-2xl border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-200">{error}</div>}
      <select
        value={selectedId}
        onChange={(event) => load(event.target.value).catch((reason) => setError(String(reason.message || reason)))}
        className="field max-w-md"
      >
        {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      {connector && (
        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <div>
              <div className="text-xs uppercase text-zinc-600">Name</div>
              <div className="mt-1 font-medium text-stone-100">{connector.name}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-zinc-600">Status</div>
              <div className="mt-1 text-zinc-300">{connector.status} / {connector.enabled ? 'enabled' : 'disabled'}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-zinc-600">Auth</div>
              <div className="mt-1 text-zinc-300">{connector.auth_type} {connector.auth_ref ? `(${connector.auth_ref})` : ''}</div>
            </div>
          </div>
          <p className="mt-4 text-sm text-zinc-400">{connector.description || 'No description.'}</p>
          <div className="mt-4"><ConnectorScopeEditor scopes={connector.scopes} /></div>
        </section>
      )}
      <ConnectorOperationTable operations={operations} />
    </div>
  );
}
