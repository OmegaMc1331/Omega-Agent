export function ScopeSelector({ scopeType, scopeId, onScopeType, onScopeId }: { scopeType: string; scopeId: string; onScopeType: (value: string) => void; onScopeId: (value: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[160px_1fr]">
      <select value={scopeType} onChange={(event) => onScopeType(event.target.value)} className="field">
        {['global', 'project', 'session', 'agent_profile'].map((item) => <option key={item}>{item}</option>)}
      </select>
      <input value={scopeId} onChange={(event) => onScopeId(event.target.value)} className="field" placeholder="scope id optional" />
    </div>
  );
}
