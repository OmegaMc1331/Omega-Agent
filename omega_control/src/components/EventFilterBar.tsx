import { Search } from 'lucide-react';

export type EventFilters = {
  type: string;
  source: string;
  level: string;
  session_id: string;
  run_id: string;
};

export function EventFilterBar({
  filters,
  types,
  onChange,
}: {
  filters: EventFilters;
  types: string[];
  onChange: (filters: EventFilters) => void;
}) {
  function set<K extends keyof EventFilters>(key: K, value: EventFilters[K]) {
    onChange({ ...filters, [key]: value });
  }
  return (
    <div className="grid gap-3 rounded-lg border border-white/10 bg-white/[0.035] p-3 md:grid-cols-5">
      <label className="text-xs text-zinc-500">
        Type
        <select className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950 px-2 py-2 text-sm text-stone-100" value={filters.type} onChange={(event) => set('type', event.target.value)}>
          <option value="">All</option>
          {types.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </label>
      <label className="text-xs text-zinc-500">
        Source
        <input className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950 px-2 py-2 text-sm text-stone-100" value={filters.source} onChange={(event) => set('source', event.target.value)} placeholder="runtime" />
      </label>
      <label className="text-xs text-zinc-500">
        Level
        <select className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950 px-2 py-2 text-sm text-stone-100" value={filters.level} onChange={(event) => set('level', event.target.value)}>
          <option value="">All</option>
          {['debug', 'info', 'warning', 'error', 'critical'].map((level) => <option key={level} value={level}>{level}</option>)}
        </select>
      </label>
      <label className="text-xs text-zinc-500">
        Session
        <div className="mt-1 flex items-center gap-2 rounded-lg border border-white/10 bg-zinc-950 px-2">
          <Search size={14} className="text-zinc-500" />
          <input className="w-full bg-transparent py-2 text-sm text-stone-100 outline-none" value={filters.session_id} onChange={(event) => set('session_id', event.target.value)} placeholder="session_id" />
        </div>
      </label>
      <label className="text-xs text-zinc-500">
        Run
        <input className="mt-1 w-full rounded-lg border border-white/10 bg-zinc-950 px-2 py-2 text-sm text-stone-100" value={filters.run_id} onChange={(event) => set('run_id', event.target.value)} placeholder="run_id" />
      </label>
    </div>
  );
}
