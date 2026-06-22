export type SkillCandidateView = {
  id: string;
  title: string;
  description: string;
  source_run_ids: string[];
  source_workflow_ids: string[];
  detected_pattern: Record<string, unknown>;
  proposed_skill: Record<string, unknown>;
  confidence: number;
  status: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type SkillView = {
  id: string;
  name: string;
  slug?: string;
  description: string;
  version: string;
  status?: string;
  skill_type?: string;
  definition?: Record<string, unknown>;
  test_cases?: Array<Record<string, unknown>>;
  source_candidate_id?: string | null;
  risk_level: string;
  enabled: boolean;
  path?: string;
  metadata?: Record<string, unknown>;
};

export type SkillTestRunView = {
  id: string;
  skill_id: string;
  version: string;
  status: string;
  results: Record<string, unknown>;
  created_at: string;
};

export type SkillDetailView = {
  skill: SkillView;
  versions: Array<{ id: string; version: string; changelog: string; created_at: string; definition: Record<string, unknown> }>;
  tests: SkillTestRunView[];
  usage: { count: number; last_used?: string | null; success_count?: number; failure_count?: number };
};
