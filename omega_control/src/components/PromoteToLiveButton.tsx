import { Play, XCircle } from 'lucide-react';

export function PromoteToLiveButton({
  disabled,
  requiresApproval,
  onPromote,
  onReject,
}: {
  disabled?: boolean;
  requiresApproval?: boolean;
  onPromote: () => void;
  onReject: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button disabled={disabled} onClick={onPromote} className="primary-button disabled:cursor-not-allowed disabled:opacity-50"><Play size={15} /> {requiresApproval ? 'Approuver et promouvoir' : 'Promote to live'}</button>
      <button disabled={disabled} onClick={onReject} className="secondary-button disabled:cursor-not-allowed disabled:opacity-50"><XCircle size={15} /> Reject</button>
    </div>
  );
}
