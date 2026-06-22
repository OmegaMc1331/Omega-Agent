export type BudgetProfileView = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  scope_type: string;
  scope_id?: string | null;
  limits: Record<string, string | number | Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type BudgetUsageView = {
  id: string;
  profile_id?: string | null;
  run_id?: string | null;
  workflow_run_id?: string | null;
  metric: string;
  used_value: number;
  limit_value?: number | null;
  status: 'ok' | 'warning' | 'exceeded';
  updated_at: string;
};

export type BudgetViolationView = {
  id: string;
  run_id?: string | null;
  workflow_run_id?: string | null;
  profile_id?: string | null;
  metric: string;
  used_value: number;
  limit_value: number;
  action_taken: string;
  reason: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type EffectiveBudgetView = {
  limits: Record<string, string | number | Record<string, unknown>>;
  profile_ids: string[];
  profile_names: string[];
  limiting_profiles: Record<string, string>;
  context: Record<string, unknown>;
};
