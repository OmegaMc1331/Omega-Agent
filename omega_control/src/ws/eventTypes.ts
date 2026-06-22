export type OmegaEvent = {
  id: string;
  event_id?: string;
  version: string;
  type: string;
  timestamp: string;
  session_id?: string | null;
  run_id?: string | null;
  step_id?: string | null;
  user_id?: string | null;
  source: string;
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical' | string;
  visibility: 'public' | 'internal' | 'redacted' | string;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type EventMessage = OmegaEvent & {
  event?: OmegaEvent;
};

export type EventConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'closed';
