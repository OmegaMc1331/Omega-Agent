export type ResearchRunView = {
  id: string;
  session_id?: string | null;
  run_id?: string | null;
  title: string;
  question: string;
  status: string;
  plan: Record<string, unknown>;
  report_markdown?: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type ResearchSourceView = {
  id: string;
  research_run_id: string;
  source_type: string;
  title: string;
  uri?: string | null;
  locator?: string | null;
  content_excerpt?: string | null;
  trust_level: string;
  collected_at: string;
  metadata: Record<string, unknown>;
};

export type ResearchClaimView = {
  id: string;
  research_run_id: string;
  claim_text: string;
  confidence: number;
  status: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type ResearchEvidenceView = {
  id: string;
  research_run_id: string;
  claim_id: string;
  source_id: string;
  quote?: string | null;
  relevance_score: number;
  supports: boolean | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type EvidenceGraphNode = {
  id: string;
  node_type: 'source' | 'claim';
  label: string;
  trust_level?: string;
  source_type?: string;
  status?: string;
  confidence?: number;
};

export type EvidenceGraphEdge = {
  id: string;
  source: string;
  target: string;
  type: 'supports' | 'contradicts' | 'mentions';
  relevance_score: number;
  quote?: string | null;
};

export type EvidenceGraphViewModel = {
  research_run_id: string;
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  confidence_summary: {
    average: number;
    total: number;
    status_counts: Record<string, number>;
  };
};

export type ResearchRunDetail = ResearchRunView & {
  sources: ResearchSourceView[];
  claims: ResearchClaimView[];
  evidence: ResearchEvidenceView[];
  graph: EvidenceGraphViewModel;
};
