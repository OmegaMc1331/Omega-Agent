const scopes = ['global', 'project', 'session', 'agent', 'run'];

export function MemoryScopeSelector({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} className="field">
      {scopes.map((scope) => <option key={scope}>{scope}</option>)}
    </select>
  );
}
