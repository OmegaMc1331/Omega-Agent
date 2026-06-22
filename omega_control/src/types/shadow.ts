export type ShadowPlanStep = {
  index: number;
  name: string;
  type: string;
  tool_name?: string | null;
  arguments: Record<string, unknown>;
  action_category: string;
  risk_level: string;
  simulable: boolean;
};

export type ShadowDiffItem = {
  path: string;
  diff: string;
  risk: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
};

export type ShadowRiskReport = {
  risk_level: string;
  files_modified: number;
  files_deleted: number;
  shell_commands: number;
  external_calls: number;
  actions_non_simulable: string[];
  policy_denials: number;
  skipped_external_actions: string[];
  budget_usage_estimated: Record<string, number>;
  budget_exceeded: string[];
  rollback_available: boolean;
  confidence: number;
  recommendation: 'promote' | 'require_approval' | 'reject';
  invariants?: { passed?: boolean };
};

export type ShadowRunView = {
  id: string;
  source_type: string;
  source_id?: string | null;
  status: string;
  objective: string;
  plan: { steps?: ShadowPlanStep[]; invariants?: string[] };
  risk_report?: ShadowRiskReport | null;
  predicted_diff?: {
    created: ShadowDiffItem[];
    modified: ShadowDiffItem[];
    deleted: ShadowDiffItem[];
    summary: string;
  } | null;
  estimated_cost?: Record<string, unknown> | null;
  created_at: string;
  completed_at?: string | null;
  steps?: Array<Record<string, unknown>>;
  promotion?: Record<string, unknown> | null;
  comparison?: {
    comparison?: {
      summary?: string;
      diff_match_score?: number;
      files?: Array<Record<string, unknown>>;
    };
    success_match?: boolean | null;
    diff_match_score?: number | null;
  } | null;
};
