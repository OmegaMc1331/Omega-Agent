export function SkillActivationToggle({
  active,
  disabled,
  onChange,
}: {
  active: boolean;
  disabled?: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onChange}
      className={`relative h-7 w-12 rounded-full border transition ${active ? 'border-emerald-400/30 bg-emerald-500/30' : 'border-white/10 bg-white/[0.06]'}`}
    >
      <span className={`absolute top-1 h-5 w-5 rounded-full bg-stone-100 transition ${active ? 'left-6' : 'left-1'}`} />
    </button>
  );
}
