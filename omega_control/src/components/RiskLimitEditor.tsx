import { RiskBadge } from './RiskBadge';

export function RiskLimitEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-2 flex items-center justify-between text-xs text-zinc-500"><span>Maximum risk</span><RiskBadge risk={value} /></span>
      <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
        {['low', 'medium', 'high', 'critical'].map((risk) => <option key={risk}>{risk}</option>)}
      </select>
    </label>
  );
}
