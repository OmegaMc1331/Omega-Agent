import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Archive,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronRight,
  CirclePlus,
  Clock3,
  Cpu,
  Database,
  FileText,
  Gauge,
  Hammer,
  HardDrive,
  History,
  Layers,
  LayoutDashboard,
  ListChecks,
  Loader2,
  MessageSquare,
  Plug,
  RefreshCw,
  ScrollText,
  Send,
  Settings,
  Shield,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react';
import { api } from './api/client';
import { ModelSelector, type CurrentModelView } from './components/ModelSelector';
import type { ModelView } from './components/ModelCard';
import type { ProviderView } from './components/ProviderCard';
import { ModelsPage, type ModelPreferenceView, type ModelUsageView } from './pages/Models';

type Page = 'Chat' | 'Sessions' | 'Models' | 'Projects' | 'Agents' | 'Delegations' | 'Channels' | 'Browser' | 'Desktop' | 'Tasks' | 'Standing Orders' | 'Tools' | 'Skills' | 'Plugins' | 'Security' | 'Approvals' | 'Jobs' | 'Memory' | 'Logs' | 'Settings';
type ProjectPolicy = {
  allowed_tools: string[];
  denied_tools: string[];
  shell_allowlist: string[];
  read_paths: string[];
  write_paths: string[];
  require_approval_for_write: boolean;
  require_approval_for_shell: boolean;
  network_allowed: boolean;
  browser_allowed: boolean;
};
type Project = { id: string; name: string; root_path: string; description: string; enabled: boolean; policy: ProjectPolicy; linked_sessions: number; updated_at: string; sessions?: Session[] };
type AgentProfile = { id: string; name: string; description: string; system_prompt: string; enabled: boolean; allowed_tools: string[]; allowed_skills: string[]; risk_level: string; policy: Record<string, unknown>; builtin?: boolean; updated_at: string };
type Channel = { id: string; type: string; name: string; enabled: boolean; status: string; configured: boolean; external: boolean; untrusted: boolean; config: Record<string, unknown>; updated_at: string };
type ScheduledTask = { id: string; title: string; prompt: string; schedule_type: string; schedule_value: string; enabled: boolean; next_run_at?: string | null; last_run_at?: string | null; metadata_json: string; updated_at: string };
type StandingOrder = { id: string; title: string; content: string; scope: string; enabled: boolean; priority: number; updated_at: string };
type Delegation = { id: string; session_id: string; parent_agent_id: string; child_agent_id: string; task: string; status: string; result: string; metadata_json: string; updated_at: string };
type Session = { id: string; title: string; status: string; active_agent_profile_id?: string | null; project_id?: string | null; created_at: string; updated_at: string };
type Message = { id?: string; role: string; content: string; created_at?: string; metadata_json?: string };
type ReasoningEvent = {
  id: string;
  session_id: string;
  message_id?: string | null;
  type: string;
  title: string;
  content: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  visibility: 'public' | 'internal' | 'redacted';
  created_at: string;
  metadata?: Record<string, unknown>;
  metadata_json?: string;
  reasoning_type?: string;
};
type Status = {
  provider: string;
  model: string;
  workspace: string;
  safe_mode: boolean;
  workspace_full_access?: boolean;
  require_approval_outside_workspace?: boolean;
  shell_full_access_in_workspace?: boolean;
  allow_delete_in_workspace?: boolean;
  allow_git_write_in_workspace?: boolean;
  reasoning_stream?: boolean;
  reasoning_detail?: string;
  fast_mode?: boolean;
  streaming?: boolean;
  perf_logging?: boolean;
  tools_count: number;
  skills_count: number;
  plugins_count: number;
  pending_approvals_count: number;
  auth_codex: { connected: boolean | null; message: string | null };
  gateway: { host: string; port: number; theme: string; open_browser: boolean };
  login_hint?: string | null;
  current_model?: CurrentModelView;
};
type Tool = { id: string; name: string; description: string; category: string; risk: string; risk_level: string; enabled: boolean; requires_approval: boolean; input_schema: unknown };
type Skill = { id: string; name: string; description: string; instructions: string; allowed_tools: string[]; risk_level: string; enabled: boolean; path: string };
type Plugin = { id: string; name: string; version: string; description: string; author?: string; trust_level: string; enabled: boolean; status: string; path: string; declares: Record<string, unknown>; permissions?: string[]; raw_manifest?: Record<string, unknown>; security_review?: { status?: string; risk_level?: string; warnings?: string[]; critical_warnings?: string[] }; error?: string };
type Approval = { id: string; action: string; tool_name: string; arguments: Record<string, unknown>; risk_level: string; reason: string; status: string; created_at: string; resolved_at?: string | null };
type Job = { id: string; title: string; status: string; kind: string; input_json: string; output_json: string; logs_json: string; updated_at: string };
type Memory = { id: string; scope: string; key: string; content: string; tags: string[]; updated_at: string };
type EventItem = { id?: string; type?: string; action?: string; payload?: Record<string, unknown>; ts?: string; created_at?: string; session_id?: string | null };
type PerformanceTrace = { trace_id: string; session_id?: string | null; message_id?: string | null; created_at: string; steps_ms: Record<string, number>; metadata: Record<string, unknown>; completed: boolean; failed: boolean };
type WsEvent = {
  type?: string;
  session_id?: string;
  message_id?: string | null;
  role?: string;
  content?: string;
  message?: string;
  payload?: Record<string, unknown>;
};
type SettingsData = Record<string, string | number | boolean | null | undefined>;
type BrowserStatus = { enabled: boolean; configured: boolean; headless: boolean; profile_dir: string; profile_valid: boolean; error: string; running: boolean; last_url: string; last_screenshot: string };
type DesktopStatus = { enabled: boolean; configured: boolean; requires_approval: boolean; screenshots_dir: string; screenshots_dir_valid: boolean; dependency_available: boolean; last_screenshot: string; error: string; warning: string };
type SecurityFinding = { severity: 'info' | 'low' | 'medium' | 'high' | 'critical'; area: string; finding: string; recommendation: string; auto_fix_available: boolean };
type SecurityReport = { score: number; generated_at: string; findings: SecurityFinding[]; fixed?: string[] };

const pages: Array<{ name: Page; label: string; icon: React.ElementType; section: 'primary' | 'advanced' }> = [
  { name: 'Chat', label: 'Chat', icon: MessageSquare, section: 'primary' },
  { name: 'Sessions', label: 'Sessions', icon: Layers, section: 'primary' },
  { name: 'Models', label: 'Models', icon: Zap, section: 'primary' },
  { name: 'Approvals', label: 'Approvals', icon: ShieldAlert, section: 'primary' },
  { name: 'Settings', label: 'Settings', icon: Settings, section: 'primary' },
  { name: 'Projects', label: 'Projects', icon: Boxes, section: 'advanced' },
  { name: 'Agents', label: 'Agents', icon: Bot, section: 'advanced' },
  { name: 'Delegations', label: 'Delegations', icon: Sparkles, section: 'advanced' },
  { name: 'Tools', label: 'Tools', icon: Hammer, section: 'advanced' },
  { name: 'Skills', label: 'Skills', icon: Sparkles, section: 'advanced' },
  { name: 'Plugins', label: 'Plugins', icon: Plug, section: 'advanced' },
  { name: 'Channels', label: 'Channels', icon: Activity, section: 'advanced' },
  { name: 'Jobs', label: 'Jobs', icon: ListChecks, section: 'advanced' },
  { name: 'Memory', label: 'Memory', icon: Database, section: 'advanced' },
  { name: 'Logs', label: 'Logs', icon: ScrollText, section: 'advanced' },
  { name: 'Security', label: 'Security', icon: Shield, section: 'advanced' },
  { name: 'Browser', label: 'Browser', icon: Gauge, section: 'advanced' },
  { name: 'Desktop', label: 'Desktop', icon: HardDrive, section: 'advanced' },
  { name: 'Tasks', label: 'Tasks', icon: Clock3, section: 'advanced' },
  { name: 'Standing Orders', label: 'Orders', icon: FileText, section: 'advanced' },
];

const primaryPages = pages.filter((item) => item.section === 'primary');
const advancedPages = pages.filter((item) => item.section === 'advanced');

const initialProjectDraft = {
  name: '',
  root_path: '',
  description: '',
  allowed_tools: 'list_files, read_file, write_file, run_shell, git_status, git_diff, git_log, remember, recall',
  denied_tools: '',
  shell_allowlist: 'pwd, ls, dir, cat, type, head, tail, pytest, git',
  read_paths: '.',
  write_paths: '.',
  require_approval_for_write: true,
  require_approval_for_shell: true,
  network_allowed: false,
  browser_allowed: false,
};

export default function App() {
  const [page, setPage] = useState<Page>('Chat');
  const [status, setStatus] = useState<Status | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [scheduledTasks, setScheduledTasks] = useState<ScheduledTask[]>([]);
  const [standingOrders, setStandingOrders] = useState<StandingOrder[]>([]);
  const [delegations, setDelegations] = useState<Delegation[]>([]);
  const [activeSession, setActiveSession] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [reasoningEvents, setReasoningEvents] = useState<ReasoningEvent[]>([]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const activeSessionRef = useRef('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [memory, setMemory] = useState<Memory[]>([]);
  const [logs, setLogs] = useState<EventItem[]>([]);
  const [performanceTraces, setPerformanceTraces] = useState<PerformanceTrace[]>([]);
  const [modelProviders, setModelProviders] = useState<ProviderView[]>([]);
  const [modelCatalog, setModelCatalog] = useState<ModelView[]>([]);
  const [modelPreferences, setModelPreferences] = useState<ModelPreferenceView[]>([]);
  const [modelUsage, setModelUsage] = useState<ModelUsageView[]>([]);
  const [recentModelRefs, setRecentModelRefs] = useState<string[]>(() => loadRecentModelRefs());
  const [currentModel, setCurrentModel] = useState<CurrentModelView | null>(null);
  const [settingsData, setSettingsData] = useState<SettingsData>({});
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null);
  const [desktopStatus, setDesktopStatus] = useState<DesktopStatus | null>(null);
  const [securityReport, setSecurityReport] = useState<SecurityReport | null>(null);
  const [securitySeverity, setSecuritySeverity] = useState('all');
  const [skillDraft, setSkillDraft] = useState({ name: '', description: '', instructions: '' });
  const [projectDraft, setProjectDraft] = useState(initialProjectDraft);
  const [taskDraft, setTaskDraft] = useState({ title: '', prompt: '', schedule_type: 'interval', schedule_value: '3600' });
  const [orderDraft, setOrderDraft] = useState({ title: '', content: '', scope: 'global', priority: 100 });
  const [jobKind, setJobKind] = useState('scan_workspace');
  const [memoryDraft, setMemoryDraft] = useState({ key: '', content: '', tags: '' });
  const [error, setError] = useState('');
  const [loadingApp, setLoadingApp] = useState(true);
  const [loadingPage, setLoadingPage] = useState(false);
  const responseStartedAtRef = useRef<number | null>(null);
  const [lastResponseMs, setLastResponseMs] = useState<number | null>(null);

  const activeTitle = useMemo(() => sessions.find((session) => session.id === activeSession)?.title || 'Nouvelle discussion', [sessions, activeSession]);
  const activeProject = useMemo(() => {
    const session = sessions.find((item) => item.id === activeSession);
    return projects.find((project) => project.id === session?.project_id) || projects.find((project) => project.id === 'default') || null;
  }, [sessions, projects, activeSession]);
  const activeAgent = useMemo(() => {
    const session = sessions.find((item) => item.id === activeSession);
    return agents.find((agent) => agent.id === session?.active_agent_profile_id) || agents.find((agent) => agent.id === 'omega-core') || null;
  }, [sessions, agents, activeSession]);
  const activeSessionEvents = useMemo(() => logs.filter((item) => item.session_id === activeSession || item.payload?.session_id === activeSession), [logs, activeSession]);
  const activeReasoningEvents = useMemo(() => reasoningEvents.filter((item) => item.session_id === activeSession), [reasoningEvents, activeSession]);
  const activeDelegations = useMemo(() => delegations.filter((item) => item.session_id === activeSession), [delegations, activeSession]);
  const pendingApprovals = useMemo(() => approvals.filter((approval) => approval.status === 'pending'), [approvals]);

  async function refreshCore() {
    const [nextStatus, nextSessions, nextApprovals, nextProjects, nextAgents, nextChannels, nextModels, nextModelProviders] = await Promise.all([
      api<Status>('/api/status'),
      api<Session[]>('/api/sessions'),
      api<Approval[]>('/api/approvals'),
      api<Project[]>('/api/projects'),
      api<AgentProfile[]>('/api/agents'),
      api<Channel[]>('/api/channels'),
      api<ModelView[]>('/api/models/catalog'),
      api<ProviderView[]>('/api/models/providers'),
    ]);
    setStatus(nextStatus);
    setCurrentModel(nextStatus.current_model || null);
    setModelCatalog(nextModels);
    setModelProviders(nextModelProviders);
    setApprovals(nextApprovals);
    setProjects(nextProjects);
    setAgents(nextAgents);
    setChannels(nextChannels);
    if (nextSessions.length === 0) {
      const session = await api<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ title: 'Nouvelle discussion' }) });
      setSessions([session]);
      setActiveSession(session.id);
    } else {
      setSessions(nextSessions);
      setActiveSession((current) => current || nextSessions[0].id);
    }
    setError('');
  }

  async function refreshPageData(target: Page) {
    setLoadingPage(true);
    try {
      if (target === 'Tools') setTools(await api<Tool[]>('/api/tools'));
      if (target === 'Models') {
        const [providers, catalog, preferences, usage, current, events] = await Promise.all([
          api<ProviderView[]>('/api/models/providers'),
          api<ModelView[]>('/api/models/catalog'),
          api<ModelPreferenceView[]>('/api/models/preferences'),
          api<ModelUsageView[]>('/api/models/usage'),
          api<CurrentModelView>(`/api/models/current${activeSession ? `?session_id=${encodeURIComponent(activeSession)}` : ''}`),
          api<EventItem[]>('/api/events?type=model.fallback'),
        ]);
        setModelProviders(providers);
        setModelCatalog(catalog);
        setModelPreferences(preferences);
        setModelUsage(usage);
        setCurrentModel(current);
        setLogs((currentLogs) => mergeEvents(currentLogs, events));
      }
      if (target === 'Skills') setSkills(await api<Skill[]>('/api/skills'));
      if (target === 'Plugins') setPlugins(await api<Plugin[]>('/api/plugins'));
      if (target === 'Projects') setProjects(await api<Project[]>('/api/projects'));
      if (target === 'Agents') setAgents(await api<AgentProfile[]>('/api/agents'));
      if (target === 'Delegations') setDelegations(await api<Delegation[]>('/api/delegations'));
      if (target === 'Channels') setChannels(await api<Channel[]>('/api/channels'));
      if (target === 'Browser') {
        setBrowserStatus(await api<BrowserStatus>('/api/browser/status'));
        setLogs(await api<EventItem[]>('/api/events'));
      }
      if (target === 'Desktop') {
        setDesktopStatus(await api<DesktopStatus>('/api/desktop/status'));
        setLogs(await api<EventItem[]>('/api/events'));
      }
      if (target === 'Tasks') {
        setScheduledTasks(await api<ScheduledTask[]>('/api/scheduled-tasks'));
        setJobs(await api<Job[]>('/api/jobs'));
      }
      if (target === 'Standing Orders') setStandingOrders(await api<StandingOrder[]>('/api/standing-orders'));
      if (target === 'Approvals') setApprovals(await api<Approval[]>('/api/approvals'));
      if (target === 'Jobs') setJobs(await api<Job[]>('/api/jobs'));
      if (target === 'Memory') setMemory(await api<Memory[]>('/api/memory'));
      if (target === 'Logs' || target === 'Chat') {
        setLogs([...(await api<EventItem[]>('/api/events')), ...(await api<EventItem[]>('/api/logs'))]);
        setDelegations(await api<Delegation[]>('/api/delegations'));
      }
      if (target === 'Sessions') setSessions(await api<Session[]>('/api/sessions'));
      if (target === 'Settings') {
        const [settings, traces] = await Promise.all([
          api<SettingsData>('/api/settings'),
          api<PerformanceTrace[]>('/api/performance/recent'),
        ]);
        setSettingsData(settings);
        setPerformanceTraces(traces);
      }
      if (target === 'Security') setSecurityReport(await api<SecurityReport>('/api/security/audit'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setLoadingPage(false);
    }
  }

  useEffect(() => {
    refreshCore()
      .catch((nextError) => setError(errorMessage(nextError)))
      .finally(() => setLoadingApp(false));
  }, []);

  useEffect(() => {
    if (!activeSession) return;
    activeSessionRef.current = activeSession;
    api<Message[]>(`/api/sessions/${activeSession}/messages`).then(setMessages).catch(() => setMessages([]));
    api<ReasoningEvent[]>(`/api/sessions/${activeSession}/reasoning`)
      .then((events) => setReasoningEvents((current) => mergeReasoningEvents(current.filter((event) => event.session_id !== activeSession), events)))
      .catch(() => setReasoningEvents((current) => current.filter((event) => event.session_id !== activeSession)));
    api<CurrentModelView>(`/api/models/current?session_id=${encodeURIComponent(activeSession)}`).then(setCurrentModel).catch(() => undefined);
  }, [activeSession]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
    socketRef.current = socket;
    socket.onmessage = (event) => {
      const data = parseWsEvent(event.data);
      if (!data) return;
      const sessionId = String(data.session_id || data.payload?.session_id || '');
      if (sessionId && sessionId !== activeSessionRef.current) return;
      if (isReasoningWsEvent(data)) {
        const reasoning = normalizeReasoningEvent(data);
        if (!reasoning) return;
        setReasoningEvents((current) => mergeReasoningEvents(current, [reasoning]));
        if (reasoning.message_id) {
          setMessages((current) => attachLatestUserMessageId(current, reasoning.message_id || ''));
        }
        return;
      }
      if (data.type === 'status.updated') {
        const status = String(data.payload?.status || data.message || '');
        if (status === 'thinking' || status.includes('reflechit') || status.includes('réfléchit')) setThinking(true);
        if (status === 'idle') setThinking(false);
        return;
      }
      if (data.type === 'message.accepted') {
        setThinking(true);
        return;
      }
      if (data.type === 'message.created') {
        const role = String(data.role || data.payload?.role || '');
        const content = String(data.content || data.payload?.content || '');
        if (role && content) setMessages((current) => [...current, { role, content }]);
        return;
      }
      if (data.type === 'message.completed') {
        const role = String(data.role || data.payload?.role || '');
        const content = String(data.content || data.payload?.content || '');
        if (role === 'assistant' && content) setMessages((current) => [...current, { role, content }]);
        setThinking(false);
        if (responseStartedAtRef.current !== null) {
          setLastResponseMs(Math.round(performance.now() - responseStartedAtRef.current));
          responseStartedAtRef.current = null;
        }
        const currentSession = activeSessionRef.current;
        if (currentSession) {
          api<Message[]>(`/api/sessions/${currentSession}/messages`).then(setMessages).catch(() => undefined);
          api<ReasoningEvent[]>(`/api/sessions/${currentSession}/reasoning`)
            .then((events) => setReasoningEvents((current) => mergeReasoningEvents(current.filter((item) => item.session_id !== currentSession), events)))
            .catch(() => undefined);
        }
        Promise.all([refreshCore(), refreshPageData('Chat')]).catch(() => undefined);
      }
      if (data.type === 'error') {
        setError(String(data.payload?.message || data.message || 'Erreur WebSocket'));
        setThinking(false);
      }
    };
    socket.onclose = () => {
      if (socketRef.current === socket) socketRef.current = null;
    };
    return () => {
      socketRef.current = null;
      socket.close();
    };
  }, []);

  useEffect(() => {
    refreshPageData(page).catch(() => undefined);
  }, [page]);

  async function newChat() {
    try {
      const session = await api<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ title: 'Nouvelle discussion' }) });
      setSessions((current) => [session, ...current]);
      setActiveSession(session.id);
      setMessages([]);
      setPage('Chat');
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function deleteSession(session: Session) {
    try {
      await api(`/api/sessions/${session.id}`, { method: 'DELETE' });
      const nextSessions = await api<Session[]>('/api/sessions');
      setSessions(nextSessions);
      setActiveSession(nextSessions[0]?.id || '');
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function setSessionProject(projectId: string) {
    if (!activeSession) return;
    try {
      const session = await api<Session>(`/api/sessions/${activeSession}/project`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId || null }),
      });
      setSessions((current) => current.map((item) => (item.id === session.id ? session : item)));
      setProjects(await api<Project[]>('/api/projects'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function setSessionAgent(agentId: string) {
    if (!activeSession) return;
    try {
      const session = await api<Session>(`/api/sessions/${activeSession}/agent`, {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId }),
      });
      setSessions((current) => current.map((item) => (item.id === session.id ? session : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function updateAgent(agent: AgentProfile, values: Partial<AgentProfile>) {
    try {
      const updated = await api<AgentProfile>(`/api/agents/${agent.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      setAgents((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function updateChannel(channel: Channel, values: Partial<Channel>) {
    try {
      const updated = await api<Channel>(`/api/channels/${channel.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      setChannels((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function testChannel(channel: Channel) {
    try {
      await api(`/api/channels/${channel.id}/test`, { method: 'POST' });
      setChannels(await api<Channel[]>('/api/channels'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function closeBrowser() {
    try {
      setBrowserStatus(await api<BrowserStatus>('/api/browser/close', { method: 'POST' }));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function setPluginEnabled(plugin: Plugin, enabled: boolean) {
    try {
      const updated = await api<Plugin>(`/api/plugins/${plugin.id}/${enabled ? 'enable' : 'disable'}`, {
        method: 'POST',
        body: enabled ? JSON.stringify({ confirmed: true }) : undefined,
      });
      setPlugins((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function rescanPlugins() {
    try {
      setPlugins(await api<Plugin[]>('/api/plugins/rescan', { method: 'POST' }));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function reloadRegistries() {
    try {
      await api('/api/registries/reload', { method: 'POST' });
      const [nextTools, nextSkills, nextPlugins, nextStatus] = await Promise.all([
        api<Tool[]>('/api/tools'),
        api<Skill[]>('/api/skills'),
        api<Plugin[]>('/api/plugins'),
        api<Status>('/api/status'),
      ]);
      setTools(nextTools);
      setSkills(nextSkills);
      setPlugins(nextPlugins);
      setStatus(nextStatus);
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function selectSessionModel(modelRef: string) {
    if (!activeSession) return;
    try {
      rememberModelRef(modelRef, setRecentModelRefs);
      await api('/api/models/select', {
        method: 'POST',
        body: JSON.stringify({ scope: 'session', scope_id: activeSession, model_ref: modelRef }),
      });
      setCurrentModel(await api<CurrentModelView>(`/api/models/current?session_id=${encodeURIComponent(activeSession)}`));
      setModelPreferences(await api<ModelPreferenceView[]>('/api/models/preferences'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function setDefaultModel(modelRef: string) {
    try {
      rememberModelRef(modelRef, setRecentModelRefs);
      await api('/api/models/preferences', {
        method: 'PATCH',
        body: JSON.stringify({ scope: 'global', primary_model_ref: modelRef }),
      });
      setCurrentModel(await api<CurrentModelView>(activeSession ? `/api/models/current?session_id=${encodeURIComponent(activeSession)}` : '/api/models/current'));
      setModelPreferences(await api<ModelPreferenceView[]>('/api/models/preferences'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function setModelPreference(scope: string, scopeId: string | null, primaryModelRef: string, fallbackModelRef?: string | null) {
    try {
      rememberModelRef(primaryModelRef, setRecentModelRefs);
      if (fallbackModelRef) rememberModelRef(fallbackModelRef, setRecentModelRefs);
      await api('/api/models/preferences', {
        method: 'PATCH',
        body: JSON.stringify({
          scope,
          scope_id: scopeId,
          primary_model_ref: primaryModelRef,
          fallback_model_ref: fallbackModelRef || null,
        }),
      });
      const [preferences, current] = await Promise.all([
        api<ModelPreferenceView[]>('/api/models/preferences'),
        api<CurrentModelView>(activeSession ? `/api/models/current?session_id=${encodeURIComponent(activeSession)}` : '/api/models/current'),
      ]);
      setModelPreferences(preferences);
      setCurrentModel(current);
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function refreshModelCatalog() {
    try {
      await api('/api/models/refresh', { method: 'POST' });
      const [providers, catalog, preferences, usage, current] = await Promise.all([
        api<ProviderView[]>('/api/models/providers'),
        api<ModelView[]>('/api/models/catalog'),
        api<ModelPreferenceView[]>('/api/models/preferences'),
        api<ModelUsageView[]>('/api/models/usage'),
        api<CurrentModelView>(activeSession ? `/api/models/current?session_id=${encodeURIComponent(activeSession)}` : '/api/models/current'),
      ]);
      setModelProviders(providers);
      setModelCatalog(catalog);
      setModelPreferences(preferences);
      setModelUsage(usage);
      setCurrentModel(current);
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function testModelProvider(providerId: string) {
    try {
      await api(`/api/models/providers/${providerId}/test-auth`, { method: 'POST' });
      setModelProviders(await api<ProviderView[]>('/api/models/providers'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function toggleModelProvider(providerId: string, enabled: boolean) {
    try {
      await api(`/api/models/providers/${providerId}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' });
      setModelProviders(await api<ProviderView[]>('/api/models/providers'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function runSecurityAudit() {
    try {
      setSecurityReport(await api<SecurityReport>('/api/security/audit'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function applySecurityFixes() {
    try {
      setSecurityReport(await api<SecurityReport>('/api/security/audit/fix-safe', { method: 'POST' }));
      await refreshCore();
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function createScheduledTask() {
    if (!taskDraft.prompt.trim()) return;
    try {
      await api<ScheduledTask>('/api/scheduled-tasks', {
        method: 'POST',
        body: JSON.stringify(taskDraft),
      });
      setTaskDraft({ title: '', prompt: '', schedule_type: 'interval', schedule_value: '3600' });
      setScheduledTasks(await api<ScheduledTask[]>('/api/scheduled-tasks'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function updateScheduledTask(task: ScheduledTask, values: Partial<ScheduledTask>) {
    try {
      const updated = await api<ScheduledTask>(`/api/scheduled-tasks/${task.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      setScheduledTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function runScheduledTaskNow(task: ScheduledTask) {
    try {
      await api(`/api/scheduled-tasks/${task.id}/run-now`, { method: 'POST' });
      setScheduledTasks(await api<ScheduledTask[]>('/api/scheduled-tasks'));
      setJobs(await api<Job[]>('/api/jobs'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function createStandingOrder() {
    if (!orderDraft.content.trim()) return;
    try {
      await api<StandingOrder>('/api/standing-orders', {
        method: 'POST',
        body: JSON.stringify(orderDraft),
      });
      setOrderDraft({ title: '', content: '', scope: 'global', priority: 100 });
      setStandingOrders(await api<StandingOrder[]>('/api/standing-orders'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function updateStandingOrder(order: StandingOrder, values: Partial<StandingOrder>) {
    try {
      const updated = await api<StandingOrder>(`/api/standing-orders/${order.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      });
      setStandingOrders((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || !activeSession) return;
    setInput('');
    setThinking(true);
    setLastResponseMs(null);
    responseStartedAtRef.current = performance.now();
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'chat.send', session_id: activeSession, message: text }));
      return;
    }
    setMessages((current) => [...current, { role: 'user', content: text }]);
    try {
      const response = await api<{ session_id: string; message: string }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ session_id: activeSession, message: text }),
      });
      setMessages((current) => [...current, { role: 'assistant', content: response.message }]);
      const events = await api<ReasoningEvent[]>(`/api/sessions/${activeSession}/reasoning`);
      setReasoningEvents((current) => mergeReasoningEvents(current.filter((event) => event.session_id !== activeSession), events));
      await Promise.all([refreshCore(), refreshPageData('Chat')]);
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      if (responseStartedAtRef.current !== null) {
        setLastResponseMs(Math.round(performance.now() - responseStartedAtRef.current));
        responseStartedAtRef.current = null;
      }
      setThinking(false);
    }
  }

  async function createSkill() {
    if (!skillDraft.name.trim()) return;
    try {
      await api<Skill>('/api/skills', { method: 'POST', body: JSON.stringify(skillDraft) });
      setSkillDraft({ name: '', description: '', instructions: '' });
      setSkills(await api<Skill[]>('/api/skills'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function createProject() {
    if (!projectDraft.name.trim() || !projectDraft.root_path.trim()) return;
    const policy: ProjectPolicy = {
      allowed_tools: csv(projectDraft.allowed_tools),
      denied_tools: csv(projectDraft.denied_tools),
      shell_allowlist: csv(projectDraft.shell_allowlist),
      read_paths: csv(projectDraft.read_paths),
      write_paths: csv(projectDraft.write_paths),
      require_approval_for_write: projectDraft.require_approval_for_write,
      require_approval_for_shell: projectDraft.require_approval_for_shell,
      network_allowed: projectDraft.network_allowed,
      browser_allowed: projectDraft.browser_allowed,
    };
    try {
      await api<Project>('/api/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: projectDraft.name,
          root_path: projectDraft.root_path,
          description: projectDraft.description,
          policy,
        }),
      });
      setProjectDraft((current) => ({ ...current, name: '', root_path: '', description: '' }));
      setProjects(await api<Project[]>('/api/projects'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function resolveApproval(id: string, approve: boolean) {
    try {
      await api<Approval>(`/api/approvals/${id}/${approve ? 'approve' : 'reject'}`, { method: 'POST' });
      setApprovals(await api<Approval[]>('/api/approvals'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function createJob() {
    try {
      await api<Job>('/api/jobs', { method: 'POST', body: JSON.stringify({ kind: jobKind, title: jobKind, input: { session_id: activeSession } }) });
      setJobs(await api<Job[]>('/api/jobs'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function createMemory() {
    if (!memoryDraft.content.trim()) return;
    try {
      await api<Memory>('/api/memory', {
        method: 'POST',
        body: JSON.stringify({ key: memoryDraft.key, content: memoryDraft.content, tags: memoryDraft.tags.split(',').map((tag) => tag.trim()).filter(Boolean) }),
      });
      setMemoryDraft({ key: '', content: '', tags: '' });
      setMemory(await api<Memory[]>('/api/memory'));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  async function patchSettings(values: Record<string, unknown>) {
    try {
      setSettingsData(await api<SettingsData>('/api/settings', { method: 'PATCH', body: JSON.stringify({ values }) }));
      setError('');
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  }

  if (loadingApp) {
    return <AppShellSkeleton />;
  }

  return (
    <div className="min-h-screen bg-[var(--omega-bg)] text-stone-100">
      <div className="grid min-h-screen grid-cols-[260px_minmax(0,1fr)] max-md:grid-cols-1">
        <Sidebar page={page} setPage={setPage} sessions={sessions} activeSession={activeSession} setActiveSession={setActiveSession} newChat={newChat} />

        <main className="min-w-0 bg-[var(--omega-main)]">
          <Topbar page={page} activeTitle={activeTitle} activeProject={activeProject} activeAgent={activeAgent} agents={agents} setSessionAgent={setSessionAgent} status={status} currentModel={currentModel} modelCatalog={modelCatalog} modelProviders={modelProviders} recentModelRefs={recentModelRefs} selectModel={selectSessionModel} setDefaultModel={setDefaultModel} pendingApprovals={pendingApprovals.length} refresh={() => refreshPageData(page)} loading={loadingPage} />
          {error && <ErrorBanner message={error} />}
          <div className="animate-fade-in">
            {page === 'Chat' && <ChatView messages={messages} reasoningEvents={activeReasoningEvents} events={activeSessionEvents} delegations={activeDelegations} approvals={pendingApprovals} input={input} thinking={thinking} lastResponseMs={lastResponseMs} projects={projects} agents={agents} activeProject={activeProject} activeAgent={activeAgent} setSessionProject={setSessionProject} setSessionAgent={setSessionAgent} setInput={setInput} sendMessage={sendMessage} resolveApproval={resolveApproval} />}
            {page === 'Sessions' && <SessionsView sessions={sessions} projects={projects} activeSession={activeSession} setActiveSession={setActiveSession} deleteSession={deleteSession} />}
            {page === 'Models' && <ModelsPage providers={modelProviders} models={modelCatalog} preferences={modelPreferences} usage={modelUsage} modelEvents={logs.filter((event) => event.type === 'model.fallback' || event.type === 'model.error')} projects={projects} agents={agents} current={currentModel} loading={loadingPage} onSelectSession={selectSessionModel} onSetDefault={setDefaultModel} onSetPreference={setModelPreference} onRefresh={refreshModelCatalog} onTestProvider={testModelProvider} onToggleProvider={toggleModelProvider} />}
            {page === 'Projects' && <ProjectsView projects={projects} sessions={sessions} draft={projectDraft} setDraft={setProjectDraft} createProject={createProject} loading={loadingPage} />}
            {page === 'Agents' && <AgentsView agents={agents} updateAgent={updateAgent} loading={loadingPage} />}
            {page === 'Delegations' && <DelegationsView delegations={delegations} loading={loadingPage} />}
            {page === 'Channels' && <ChannelsView channels={channels} updateChannel={updateChannel} testChannel={testChannel} loading={loadingPage} />}
            {page === 'Browser' && <BrowserView status={browserStatus} events={logs.filter((event) => event.type?.startsWith('browser.'))} closeBrowser={closeBrowser} loading={loadingPage} />}
            {page === 'Desktop' && <DesktopView status={desktopStatus} events={logs.filter((event) => event.type?.startsWith('desktop.'))} loading={loadingPage} />}
            {page === 'Tasks' && <TasksView tasks={scheduledTasks} jobs={jobs} draft={taskDraft} setDraft={setTaskDraft} createTask={createScheduledTask} updateTask={updateScheduledTask} runNow={runScheduledTaskNow} loading={loadingPage} />}
            {page === 'Standing Orders' && <StandingOrdersView orders={standingOrders} draft={orderDraft} setDraft={setOrderDraft} createOrder={createStandingOrder} updateOrder={updateStandingOrder} loading={loadingPage} />}
            {page === 'Tools' && <ToolsView tools={tools} loading={loadingPage} />}
            {page === 'Skills' && <SkillsView skills={skills} draft={skillDraft} setDraft={setSkillDraft} createSkill={createSkill} refresh={() => refreshPageData('Skills')} loading={loadingPage} />}
            {page === 'Plugins' && <PluginsView plugins={plugins} setPluginEnabled={setPluginEnabled} rescanPlugins={rescanPlugins} loading={loadingPage} />}
            {page === 'Security' && <SecurityView report={securityReport} severity={securitySeverity} setSeverity={setSecuritySeverity} runAudit={runSecurityAudit} applyFixes={applySecurityFixes} loading={loadingPage} />}
            {page === 'Approvals' && <ApprovalsView approvals={approvals} resolveApproval={resolveApproval} loading={loadingPage} />}
            {page === 'Jobs' && <JobsView jobs={jobs} jobKind={jobKind} setJobKind={setJobKind} createJob={createJob} loading={loadingPage} />}
            {page === 'Memory' && <MemoryView memory={memory} draft={memoryDraft} setDraft={setMemoryDraft} createMemory={createMemory} refresh={() => refreshPageData('Memory')} loading={loadingPage} />}
            {page === 'Logs' && <LogsView logs={logs} loading={loadingPage} />}
            {page === 'Settings' && <SettingsView status={status} settingsData={settingsData} performanceTraces={performanceTraces} reloadRegistries={reloadRegistries} patchSettings={patchSettings} loading={loadingPage} />}
          </div>
        </main>

      </div>
    </div>
  );
}

function Sidebar({ page, setPage, sessions, activeSession, setActiveSession, newChat }: { page: Page; setPage: (page: Page) => void; sessions: Session[]; activeSession: string; setActiveSession: (id: string) => void; newChat: () => void }) {
  return (
    <aside className="sticky top-0 flex h-screen flex-col border-r border-white/10 bg-[var(--omega-sidebar)] p-4 max-md:static max-md:h-auto max-md:border-b max-md:border-r-0">
      <div className="mb-6 flex items-center gap-3 px-1">
        <div className="grid h-10 w-10 place-items-center rounded-2xl border border-white/10 bg-white/[0.045] text-lg font-semibold text-stone-100">Ω</div>
        <div>
          <div className="text-sm font-semibold tracking-wide text-stone-100">Ω Omega</div>
          <div className="text-xs text-zinc-500">Omega Control</div>
        </div>
      </div>

      <button onClick={newChat} className="primary-button mb-5 w-full">
        <CirclePlus size={17} /> Nouveau chat
      </button>

      <div className="mb-5 border-t border-white/10 pt-4 max-md:hidden">
        <div className="mb-2 px-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-600">Récent</div>
        <div className="max-h-28 space-y-1 overflow-auto">
          {sessions.slice(0, 3).map((session) => (
            <button key={session.id} onClick={() => setActiveSession(session.id)} className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs transition ${session.id === activeSession ? 'bg-white/[0.075] text-stone-100' : 'text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200'}`}>
              <MessageSquare size={14} />
              <span className="min-w-0 flex-1 truncate">{session.title}</span>
            </button>
          ))}
          {sessions.length === 0 && <div className="px-2 py-4 text-center text-xs text-zinc-600">Aucune session</div>}
        </div>
      </div>

      <nav className="overflow-auto pr-1">
        <div className="grid gap-1">
          {primaryPages.map(({ name, label, icon: Icon }) => (
            <button key={name} onClick={() => setPage(name)} className={`group flex h-10 items-center gap-3 rounded-2xl px-3 text-sm transition ${page === name ? 'bg-white/[0.085] text-stone-100 shadow-inset-line' : 'text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200'}`}>
              <Icon size={17} className={page === name ? 'text-blue-300/90' : 'text-zinc-600 group-hover:text-zinc-300'} />
              <span className="min-w-0 flex-1 text-left">{label}</span>
              {page === name && <ChevronRight size={15} className="text-zinc-500" />}
            </button>
          ))}
        </div>

        <details className="mt-4" open={advancedPages.some((item) => item.name === page)}>
          <summary className="flex h-9 cursor-pointer list-none items-center justify-between rounded-2xl px-3 text-xs font-medium uppercase tracking-[0.13em] text-zinc-600 transition hover:bg-white/[0.04] hover:text-zinc-400">
            Avancé
            <ChevronRight size={14} />
          </summary>
          <div className="mt-1 grid gap-1">
            {advancedPages.map(({ name, label, icon: Icon }) => (
              <button key={name} onClick={() => setPage(name)} className={`group flex h-9 items-center gap-3 rounded-2xl px-3 text-sm transition ${page === name ? 'bg-white/[0.075] text-stone-100 shadow-inset-line' : 'text-zinc-600 hover:bg-white/[0.045] hover:text-zinc-300'}`}>
                <Icon size={16} className={page === name ? 'text-zinc-300' : 'text-zinc-700 group-hover:text-zinc-400'} />
                <span className="min-w-0 flex-1 text-left">{label}</span>
              </button>
            ))}
          </div>
        </details>
      </nav>
    </aside>
  );
}

function Topbar({ page, activeTitle, activeProject, activeAgent, agents, setSessionAgent, status, currentModel, modelCatalog, modelProviders, recentModelRefs, selectModel, setDefaultModel, pendingApprovals, refresh, loading }: { page: Page; activeTitle: string; activeProject: Project | null; activeAgent: AgentProfile | null; agents: AgentProfile[]; setSessionAgent: (agentId: string) => void; status: Status | null; currentModel: CurrentModelView | null; modelCatalog: ModelView[]; modelProviders: ProviderView[]; recentModelRefs: string[]; selectModel: (modelRef: string) => void; setDefaultModel: (modelRef: string) => void; pendingApprovals: number; refresh: () => void; loading: boolean }) {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-[rgba(16,17,20,0.82)] px-6 py-3.5 backdrop-blur-xl max-sm:px-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <LayoutDashboard size={14} />
            <span>Omega Control</span>
            <span className="text-zinc-700">/</span>
            <span>{page}</span>
          </div>
          <h1 className="mt-1 truncate text-lg font-semibold tracking-tight text-stone-100">{page === 'Chat' ? activeTitle : `Omega ${page}`}</h1>
        </div>
        <div className="flex items-center gap-2 max-md:hidden">
          {page === 'Chat' && <ModelSelector current={currentModel} models={modelCatalog} providers={modelProviders} recentModelRefs={recentModelRefs} onSelect={selectModel} onSetDefault={setDefaultModel} />}
          {page !== 'Chat' && <StatusPill icon={Cpu} label={status?.provider || 'provider'} tone="cyan" />}
          {page !== 'Chat' && <StatusPill icon={Zap} label={status?.model || 'model'} tone="violet" />}
          <StatusPill icon={Boxes} label={activeProject?.name || 'Default Workspace'} tone={activeProject?.enabled === false ? 'amber' : 'slate'} />
          {page !== 'Chat' && (
            <select value={activeAgent?.id || 'omega-core'} onChange={(event) => setSessionAgent(event.target.value)} className="field h-9 max-w-[180px] py-1 text-xs">
              {agents.filter((agent) => agent.enabled).map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          )}
          {page !== 'Chat' && <StatusPill icon={Shield} label={status?.auth_codex.connected ? 'Codex OK' : 'Codex off'} tone={status?.auth_codex.connected ? 'green' : 'amber'} />}
          <StatusPill icon={ShieldAlert} label={`${pendingApprovals} approvals`} tone={pendingApprovals ? 'amber' : 'slate'} />
          <button onClick={refresh} className="grid h-9 w-9 place-items-center rounded-2xl border border-white/10 bg-white/[0.045] text-zinc-300 transition hover:bg-white/[0.075]" aria-label="Refresh">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
    </header>
  );
}

function ChatView({ messages, reasoningEvents, events, delegations, approvals, input, thinking, lastResponseMs, projects, agents, activeProject, activeAgent, setSessionProject, setSessionAgent, setInput, sendMessage, resolveApproval }: { messages: Message[]; reasoningEvents: ReasoningEvent[]; events: EventItem[]; delegations: Delegation[]; approvals: Approval[]; input: string; thinking: boolean; lastResponseMs: number | null; projects: Project[]; agents: AgentProfile[]; activeProject: Project | null; activeAgent: AgentProfile | null; setSessionProject: (projectId: string) => void; setSessionAgent: (agentId: string) => void; setInput: (value: string) => void; sendMessage: () => void; resolveApproval: (id: string, approve: boolean) => void }) {
  const toolEvents = events.filter((event) => event.type?.startsWith('tool.') || event.type?.startsWith('approval.'));
  const latestReasoning = reasoningEvents.slice(-12);
  return (
    <section className="grid h-[calc(100vh-65px)] grid-rows-[minmax(0,1fr)_auto]">
      <div className="overflow-y-auto px-6 py-9 max-sm:px-4">
        <div className="mx-auto max-w-3xl space-y-8">
          <details className="group rounded-[22px] border border-white/[0.08] bg-white/[0.022] px-4 py-3 text-sm text-zinc-400">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2">
                <Boxes size={15} className="text-zinc-500" />
                <span className="truncate">{activeProject?.name || 'Default Workspace'}</span>
                <span className="text-zinc-700">·</span>
                <span className="truncate">{activeAgent?.name || 'Omega Core'}</span>
              </span>
              <ChevronRight size={15} className="shrink-0 text-zinc-600 transition group-open:rotate-90" />
            </summary>
            <div className="mt-3 grid gap-3 border-t border-white/[0.08] pt-3 sm:grid-cols-2">
              <select value={activeProject?.id || 'default'} onChange={(event) => setSessionProject(event.target.value)} className="field h-10 py-1 text-sm">
                {projects.filter((project) => project.enabled).map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
              <select value={activeAgent?.id || 'omega-core'} onChange={(event) => setSessionAgent(event.target.value)} className="field h-10 py-1 text-sm">
                {agents.filter((agent) => agent.enabled).map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
              </select>
            </div>
          </details>
          {messages.length === 0 && !thinking && <ChatEmptyState setInput={setInput} />}
          {messages.map((message, index) => {
            const previousUser = [...messages.slice(0, index)].reverse().find((item) => item.role === 'user');
            const attachedReasoning = previousUser?.id ? reasoningEvents.filter((event) => event.message_id === previousUser.id) : [];
            const liveReasoning = message.role === 'assistant' && index === messages.length - 1 ? latestReasoning : [];
            return <MessageBubble key={message.id || index} message={message} reasoningEvents={attachedReasoning.length ? attachedReasoning : liveReasoning} />;
          })}
          {delegations.length > 0 && <DelegationCards delegations={delegations.slice(0, 4)} />}
          {toolEvents.length > 0 && <ToolEventStrip events={toolEvents.slice(0, 6)} />}
          {approvals.length > 0 && <InlineApprovals approvals={approvals} resolveApproval={resolveApproval} />}
          {thinking && <ThinkingIndicator events={latestReasoning} />}
          {!thinking && lastResponseMs !== null && <div className="px-12 text-xs text-zinc-600 max-sm:px-0">Réponse en {formatDurationMs(lastResponseMs)}</div>}
        </div>
      </div>
      <Composer input={input} setInput={setInput} sendMessage={sendMessage} thinking={thinking} />
    </section>
  );
}

function MessageBubble({ message, reasoningEvents = [] }: { message: Message; reasoningEvents?: ReasoningEvent[] }) {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';
  const [open, setOpen] = useState(false);
  if (isTool) {
    return (
      <div className="ml-12 flex items-center gap-2 text-xs text-zinc-500">
        <TerminalSquare size={14} className="text-zinc-600" />
        <span className="rounded-full border border-white/10 bg-white/[0.035] px-2.5 py-1">Tool</span>
        <span className="min-w-0 truncate">{message.content}</span>
      </div>
    );
  }
  return (
    <div className={`flex gap-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <Avatar icon={Bot} tone="slate" />}
      <div className={`min-w-0 ${isUser ? 'max-w-[76%]' : 'max-w-full flex-1'}`}>
        <div className={`${isUser ? 'rounded-[24px] bg-white/[0.085] px-4 py-3.5 text-stone-100 shadow-inset-line' : 'px-0 py-1 text-stone-100'} text-[15px] leading-7`}>
          {isUser && <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-500">Vous</div>}
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        </div>
        {!isUser && reasoningEvents.length > 0 && (
          <div className="mt-3">
            <button onClick={() => setOpen((current) => !current)} className="inline-flex h-8 items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 text-xs text-zinc-400 transition hover:bg-white/[0.06] hover:text-zinc-200">
              <ChevronRight size={14} className={`transition ${open ? 'rotate-90' : ''}`} />
              Raisonnement
            </button>
            {open && <ReasoningPanel events={reasoningEvents} />}
          </div>
        )}
      </div>
    </div>
  );
}

function ReasoningPanel({ events }: { events: ReasoningEvent[] }) {
  return (
    <div className="mt-2 rounded-3xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-stone-100"><Sparkles size={15} className="text-zinc-400" /> Raisonnement</div>
        <Badge tone="slate">compact</Badge>
      </div>
      <div className="relative ml-3 border-l border-white/10 pl-5">
        {events.map((event) => {
          const Icon = reasoningIcon(event.type);
          return (
            <div key={event.id} className="relative mb-4 last:mb-0">
              <div className={`absolute -left-[29px] top-1 grid h-5 w-5 place-items-center rounded-full border ${reasoningDotClass(event.status)}`}>
                <Icon size={12} />
              </div>
              <div className="rounded-2xl border border-white/10 bg-black/10 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={reasoningBadgeTone(event.type)}>{reasoningBadgeLabel(event.type)}</Badge>
                  <span className="text-sm font-medium text-stone-100">{event.title}</span>
                  <span className="text-xs text-zinc-600">{formatDate(event.created_at)}</span>
                  <span className={`ml-auto text-xs ${event.status === 'running' ? 'animate-pulse text-blue-200' : event.status === 'failed' ? 'text-red-300' : 'text-zinc-500'}`}>{event.status}</span>
                </div>
                {event.content && <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-zinc-400">{event.content}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function reasoningIcon(type: string): React.ElementType {
  if (type.includes('tool')) return TerminalSquare;
  if (type.includes('approval')) return ShieldAlert;
  if (type.includes('plan')) return ListChecks;
  if (type.includes('observation')) return FileText;
  if (type.includes('summary') || type.includes('completed')) return CheckCircle2;
  if (type.includes('error')) return AlertTriangle;
  return Sparkles;
}

function reasoningBadgeLabel(type: string) {
  if (type.includes('analysis')) return 'analysis';
  if (type.includes('plan')) return 'plan';
  if (type.includes('tool')) return 'tool';
  if (type.includes('approval')) return 'approval';
  if (type.includes('observation')) return 'observation';
  if (type.includes('summary')) return 'summary';
  return 'reasoning';
}

function reasoningBadgeTone(type: string): 'slate' | 'cyan' | 'green' | 'amber' | 'red' | 'violet' {
  if (type.includes('tool')) return 'violet';
  if (type.includes('approval')) return 'amber';
  if (type.includes('observation')) return 'green';
  if (type.includes('error')) return 'red';
  if (type.includes('summary')) return 'cyan';
  return 'slate';
}

function reasoningDotClass(status: string) {
  if (status === 'running') return 'border-blue-400/30 bg-blue-500/10 text-blue-200 animate-pulse';
  if (status === 'failed') return 'border-red-400/35 bg-red-500/10 text-red-200';
  if (status === 'pending') return 'border-amber-400/35 bg-amber-400/10 text-amber-200 animate-pulse';
  return 'border-white/10 bg-white/[0.055] text-zinc-300';
}

function ToolEventStrip({ events }: { events: EventItem[] }) {
  return (
    <div className="space-y-1.5 px-12 max-sm:px-0">
      <div className="flex items-center gap-2 text-xs text-zinc-600"><TerminalSquare size={13} /> Activité</div>
      <div className="grid gap-1.5">
        {events.map((event, index) => (
          <div key={event.id || index} className="flex min-w-0 items-center gap-2 text-xs text-zinc-500">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-300/70" />
            <span className="shrink-0 font-medium text-zinc-300">{event.type || event.action}</span>
            <span className="min-w-0 truncate text-zinc-600">{stringifyCompact(event.payload || {})}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DelegationCards({ delegations }: { delegations: Delegation[] }) {
  return (
    <div className="rounded-2xl border border-violet-400/15 bg-violet-400/8 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-violet-200"><Sparkles size={17} /> Delegations</div>
      <div className="grid gap-3">
        {delegations.map((delegation) => (
          <div key={delegation.id} className="rounded-2xl border border-white/10 bg-black/15 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-stone-100">{delegation.parent_agent_id} &rarr; {delegation.child_agent_id}</div>
                <p className="mt-1 text-sm text-zinc-300">{delegation.task}</p>
              </div>
              <Badge tone={delegation.status === 'completed' ? 'green' : delegation.status === 'failed' ? 'red' : 'violet'}>{delegation.status}</Badge>
            </div>
            {delegation.result && <pre className="mt-3 max-h-32 overflow-auto rounded-xl bg-black/20 p-2 text-xs text-zinc-500">{delegation.result}</pre>}
          </div>
        ))}
      </div>
    </div>
  );
}

function InlineApprovals({ approvals, resolveApproval }: { approvals: Approval[]; resolveApproval: (id: string, approve: boolean) => void }) {
  return (
    <div className="rounded-3xl border border-amber-400/20 bg-amber-400/8 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-amber-100"><ShieldAlert size={17} /> Approval required</div>
      <div className="grid gap-3">
        {approvals.map((approval) => (
          <div key={approval.id} className="rounded-2xl border border-white/10 bg-black/10 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-medium text-stone-100">{approval.tool_name || approval.action}</div>
                <div className="mt-1 text-xs text-zinc-500">{approval.reason || 'Action sensible en attente de validation.'}</div>
              </div>
              <RiskBadge risk={approval.risk_level} />
            </div>
            <pre className="mt-3 max-h-28 overflow-auto p-3 text-xs text-zinc-400">{JSON.stringify(approval.arguments, null, 2)}</pre>
            <div className="mt-3 flex gap-2">
              <button onClick={() => resolveApproval(approval.id, true)} className="primary-button h-9"><CheckCircle2 size={16} /> Approuver</button>
              <button onClick={() => resolveApproval(approval.id, false)} className="secondary-button h-9"><XCircle size={16} /> Refuser</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Composer({ input, setInput, sendMessage, thinking }: { input: string; setInput: (value: string) => void; sendMessage: () => void; thinking: boolean }) {
  return (
    <div className="bg-gradient-to-t from-[var(--omega-main)] via-[rgba(16,17,20,0.94)] to-transparent p-5 pt-10 backdrop-blur">
      <div className="mx-auto max-w-3xl rounded-[28px] border border-white/10 bg-[#16171b]/95 p-2 shadow-soft ring-1 ring-white/[0.03]">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            rows={2}
            className="min-h-14 flex-1 resize-none rounded-[22px] border border-transparent bg-transparent px-4 py-3.5 text-[15px] leading-6 text-stone-100 outline-none placeholder:text-zinc-500 focus:border-white/10"
            placeholder="Message à Omega..."
          />
          <button disabled={thinking || !input.trim()} onClick={sendMessage} className="mb-1 grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-blue-500 text-stone-100 shadow-sm transition hover:bg-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-300/35 disabled:cursor-not-allowed disabled:opacity-45" aria-label="Envoyer">
            {thinking ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}

function SessionsView({ sessions, projects, activeSession, setActiveSession, deleteSession }: { sessions: Session[]; projects: Project[]; activeSession: string; setActiveSession: (id: string) => void; deleteSession: (session: Session) => void }) {
  if (sessions.length === 0) return <PageFrame><EmptyState icon={Layers} title="Aucune session" body="Les conversations persistantes apparaîtront ici." /></PageFrame>;
  return (
    <PageFrame>
      <div className="grid gap-3">
        {sessions.map((session) => (
          <Card key={session.id} interactive={session.id !== activeSession}>
            <div className="flex items-center justify-between gap-4">
              <button onClick={() => setActiveSession(session.id)} className="min-w-0 text-left">
                <div className="truncate font-semibold text-stone-100">{session.title}</div>
                <div className="mt-1 text-sm text-zinc-500">{session.status} · {projectName(projects, session.project_id)} · {formatDate(session.updated_at)}</div>
              </button>
              <div className="flex items-center gap-2">
                <Badge>{session.id === activeSession ? 'active' : 'idle'}</Badge>
                <button onClick={() => deleteSession(session)} className="grid h-9 w-9 place-items-center rounded-2xl border border-white/10 text-zinc-500 transition hover:border-red-400/30 hover:text-red-300" aria-label="Supprimer"><Trash2 size={16} /></button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function ProjectsView({ projects, sessions, draft, setDraft, createProject, loading }: { projects: Project[]; sessions: Session[]; draft: typeof initialProjectDraft; setDraft: (value: typeof initialProjectDraft) => void; createProject: () => void; loading: boolean }) {
  const preview: ProjectPolicy = {
    allowed_tools: csv(draft.allowed_tools),
    denied_tools: csv(draft.denied_tools),
    shell_allowlist: csv(draft.shell_allowlist),
    read_paths: csv(draft.read_paths),
    write_paths: csv(draft.write_paths),
    require_approval_for_write: draft.require_approval_for_write,
    require_approval_for_shell: draft.require_approval_for_shell,
    network_allowed: draft.network_allowed,
    browser_allowed: draft.browser_allowed,
  };
  return (
    <PageFrame>
      <div className="grid gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
        <Card>
          <SectionHeader icon={Boxes} title="Create project" subtitle="Root, permissions and runtime policy for a local workspace." compact />
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="field mb-3" placeholder="Project name" />
          <input value={draft.root_path} onChange={(e) => setDraft({ ...draft, root_path: e.target.value })} className="field mb-3" placeholder="Root path" />
          <textarea value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} rows={3} className="field mb-3" placeholder="Description" />
          <div className="grid gap-3 md:grid-cols-2">
            <input value={draft.allowed_tools} onChange={(e) => setDraft({ ...draft, allowed_tools: e.target.value })} className="field" placeholder="Allowed tools" />
            <input value={draft.denied_tools} onChange={(e) => setDraft({ ...draft, denied_tools: e.target.value })} className="field" placeholder="Denied tools" />
            <input value={draft.read_paths} onChange={(e) => setDraft({ ...draft, read_paths: e.target.value })} className="field" placeholder="Read paths" />
            <input value={draft.write_paths} onChange={(e) => setDraft({ ...draft, write_paths: e.target.value })} className="field" placeholder="Write paths" />
            <input value={draft.shell_allowlist} onChange={(e) => setDraft({ ...draft, shell_allowlist: e.target.value })} className="field md:col-span-2" placeholder="Shell allowlist" />
          </div>
          <div className="mt-4 grid gap-2 text-sm text-zinc-300">
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.require_approval_for_write} onChange={(e) => setDraft({ ...draft, require_approval_for_write: e.target.checked })} /> Require approval for write</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.require_approval_for_shell} onChange={(e) => setDraft({ ...draft, require_approval_for_shell: e.target.checked })} /> Require approval for shell</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.network_allowed} onChange={(e) => setDraft({ ...draft, network_allowed: e.target.checked })} /> Network allowed</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={draft.browser_allowed} onChange={(e) => setDraft({ ...draft, browser_allowed: e.target.checked })} /> Browser allowed</label>
          </div>
          <pre className="mt-4 max-h-48 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{JSON.stringify(preview, null, 2)}</pre>
          <button onClick={createProject} className="primary-button mt-4"><CirclePlus size={16} /> Create project</button>
        </Card>

        <section className="grid gap-3">
          {loading && <LoadingGrid />}
          {!loading && projects.map((project) => {
            const linked = sessions.filter((session) => session.project_id === project.id);
            return (
              <Card key={project.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 font-semibold text-stone-100"><Boxes size={17} className="text-blue-300" /> {project.name}</div>
                    <div className="mt-1 break-words text-sm text-zinc-500">{project.root_path}</div>
                    {project.description && <p className="mt-2 text-sm leading-6 text-zinc-500">{project.description}</p>}
                  </div>
                  <div className="flex gap-2"><Badge tone={project.enabled ? 'green' : 'red'}>{project.enabled ? 'enabled' : 'disabled'}</Badge><Badge>{project.linked_sessions} sessions</Badge></div>
                </div>
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  <pre className="max-h-44 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{JSON.stringify(project.policy, null, 2)}</pre>
                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-600">Linked sessions</div>
                    <div className="grid gap-2">
                      {linked.length === 0 && <div className="text-sm text-zinc-600">No linked session</div>}
                      {linked.map((session) => <div key={session.id} className="truncate rounded-xl bg-white/5 px-3 py-2 text-sm text-zinc-300">{session.title}</div>)}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </section>
      </div>
    </PageFrame>
  );
}

function AgentsView({ agents, updateAgent, loading }: { agents: AgentProfile[]; updateAgent: (agent: AgentProfile, values: Partial<AgentProfile>) => void; loading: boolean }) {
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={Bot} title="Agent profiles" subtitle="System prompts, tools, skills and risk policy per specialized profile." />
      <div className="grid gap-3 xl:grid-cols-2">
        {agents.map((agent) => <AgentEditor key={agent.id} agent={agent} updateAgent={updateAgent} />)}
      </div>
    </PageFrame>
  );
}

function DelegationsView({ delegations, loading }: { delegations: Delegation[]; loading: boolean }) {
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  if (delegations.length === 0) return <PageFrame><EmptyState icon={Sparkles} title="Aucune delegation" body="Les sous-taches deleguees aux profils agents apparaitront ici." /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={Sparkles} title="Delegations" subtitle="Sous-taches executees en contexte limite avec policies heritees." />
      <div className="grid gap-3 xl:grid-cols-2">
        {delegations.map((delegation) => (
          <Card key={delegation.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-stone-100">{delegation.parent_agent_id} &rarr; {delegation.child_agent_id}</div>
                <div className="mt-1 text-xs text-zinc-600">{formatDate(delegation.updated_at)}</div>
              </div>
              <Badge tone={delegation.status === 'completed' ? 'green' : delegation.status === 'failed' ? 'red' : 'violet'}>{delegation.status}</Badge>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-300">{delegation.task}</p>
            <pre className="mt-3 max-h-44 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{delegation.result || delegation.metadata_json}</pre>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function ChannelsView({ channels, updateChannel, testChannel, loading }: { channels: Channel[]; updateChannel: (channel: Channel, values: Partial<Channel>) => void; testChannel: (channel: Channel) => void; loading: boolean }) {
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  if (channels.length === 0) return <PageFrame><EmptyState icon={Activity} title="Aucun channel" body="Le registre channels est vide ou indisponible." /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={Activity} title="Channels" subtitle="Entrées multi-channel routées par Omega Gateway, sessions et policies." />
      <div className="grid gap-3 xl:grid-cols-2">
        {channels.map((channel) => (
          <Card key={channel.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 font-semibold text-stone-100"><Activity size={17} className="text-blue-300" /> {channel.name}</div>
                <div className="mt-1 text-xs text-zinc-600">{channel.id} · {channel.type}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={channel.enabled ? 'green' : 'slate'}>{channel.enabled ? 'enabled' : 'disabled'}</Badge>
                <Badge tone={channel.status === 'not_configured' || channel.status === 'error' ? 'amber' : channel.configured ? 'green' : 'slate'}>{channel.status}</Badge>
                {channel.untrusted && <Badge tone="amber">untrusted</Badge>}
              </div>
            </div>
            <pre className="mt-4 max-h-40 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{JSON.stringify(channel.config, null, 2)}</pre>
            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={() => updateChannel(channel, { enabled: !channel.enabled })} className="secondary-button">{channel.enabled ? 'Disable' : 'Enable'}</button>
              <button onClick={() => testChannel(channel)} className="secondary-button">Test</button>
            </div>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function BrowserView({ status, events, closeBrowser, loading }: { status: BrowserStatus | null; events: EventItem[]; closeBrowser: () => void; loading: boolean }) {
  if (loading || !status) return <PageFrame><LoadingGrid /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={Gauge} title="Browser" subtitle="Automation Playwright locale avec profil isole et approvals sensibles." />
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="font-semibold text-stone-100">Runtime</div>
            <div className="flex flex-wrap gap-2">
              <Badge tone={status.enabled ? 'green' : 'slate'}>{status.enabled ? 'enabled' : 'disabled'}</Badge>
              <Badge tone={status.configured ? 'green' : status.error ? 'amber' : 'slate'}>{status.configured ? 'configured' : 'not configured'}</Badge>
              <Badge tone={status.running ? 'cyan' : 'slate'}>{status.running ? 'running' : 'closed'}</Badge>
            </div>
          </div>
          {status.error && <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">{status.error}</div>}
          <dl className="mt-4 grid gap-3 text-sm">
            <div><dt className="text-zinc-600">Mode</dt><dd className="text-zinc-200">{status.headless ? 'headless' : 'headed'}</dd></div>
            <div><dt className="text-zinc-600">Profile</dt><dd className="break-all text-zinc-300">{status.profile_dir}</dd></div>
            <div><dt className="text-zinc-600">Last URL</dt><dd className="break-all text-zinc-300">{status.last_url || 'None'}</dd></div>
            <div><dt className="text-zinc-600">Last screenshot</dt><dd className="break-all text-zinc-300">{status.last_screenshot || 'None'}</dd></div>
          </dl>
          <button onClick={closeBrowser} disabled={!status.running} className="secondary-button mt-4 disabled:cursor-not-allowed disabled:opacity-50">Close browser</button>
        </Card>
        <div className="grid gap-4">
          <Card>
            <div className="mb-3 font-semibold text-stone-100">Screenshot</div>
            {status.last_screenshot ? (
              <img src={`/api/browser/screenshot?t=${encodeURIComponent(status.last_screenshot)}`} alt="Browser screenshot" className="max-h-[520px] w-full rounded-xl border border-white/10 object-contain" />
            ) : (
              <div className="grid min-h-56 place-items-center rounded-xl border border-dashed border-white/12 bg-white/[0.03] text-sm text-zinc-600">No screenshot captured</div>
            )}
          </Card>
          <Card>
            <div className="mb-3 font-semibold text-stone-100">Events</div>
            <div className="grid gap-2">
              {events.length === 0 && <div className="text-sm text-zinc-600">No browser event</div>}
              {events.slice(0, 8).map((event, index) => (
                <div key={event.id || index} className="rounded-xl bg-white/5 px-3 py-2 text-sm text-zinc-300">
                  <span className="text-zinc-600">{formatDate(event.created_at || event.ts || '')}</span> {event.type || event.action}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </PageFrame>
  );
}

function DesktopView({ status, events, loading }: { status: DesktopStatus | null; events: EventItem[]; loading: boolean }) {
  if (loading || !status) return <PageFrame><LoadingGrid /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={HardDrive} title="Desktop" subtitle="Automation desktop experimentale, visible et soumise a approval." />
      <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="font-semibold text-stone-100">Runtime</div>
            <div className="flex flex-wrap gap-2">
              <Badge tone={status.enabled ? 'green' : 'slate'}>{status.enabled ? 'enabled' : 'disabled'}</Badge>
              <Badge tone={status.configured ? 'green' : status.error ? 'amber' : 'slate'}>{status.configured ? 'configured' : 'not configured'}</Badge>
              <Badge tone={status.requires_approval ? 'amber' : 'red'}>{status.requires_approval ? 'approval' : 'no approval'}</Badge>
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm leading-6 text-amber-100">{status.warning}</div>
          {status.error && <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{status.error}</div>}
          <dl className="mt-4 grid gap-3 text-sm">
            <div><dt className="text-zinc-600">Dependency</dt><dd className="text-zinc-200">{status.dependency_available ? 'pyautogui available' : 'pyautogui missing'}</dd></div>
            <div><dt className="text-zinc-600">Screenshots</dt><dd className="break-all text-zinc-300">{status.screenshots_dir}</dd></div>
            <div><dt className="text-zinc-600">Last screenshot</dt><dd className="break-all text-zinc-300">{status.last_screenshot || 'None'}</dd></div>
          </dl>
        </Card>
        <div className="grid gap-4">
          <Card>
            <div className="mb-3 font-semibold text-stone-100">Screenshot</div>
            {status.last_screenshot ? (
              <img src={`/api/desktop/screenshot?t=${encodeURIComponent(status.last_screenshot)}`} alt="Desktop screenshot" className="max-h-[520px] w-full rounded-xl border border-white/10 object-contain" />
            ) : (
              <div className="grid min-h-56 place-items-center rounded-xl border border-dashed border-white/12 bg-white/[0.03] text-sm text-zinc-600">No desktop screenshot captured</div>
            )}
          </Card>
          <Card>
            <div className="mb-3 font-semibold text-stone-100">Events</div>
            <div className="grid gap-2">
              {events.length === 0 && <div className="text-sm text-zinc-600">No desktop event</div>}
              {events.slice(0, 8).map((event, index) => (
                <div key={event.id || index} className="rounded-xl bg-white/5 px-3 py-2 text-sm text-zinc-300">
                  <span className="text-zinc-600">{formatDate(event.created_at || event.ts || '')}</span> {event.type || event.action}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </PageFrame>
  );
}

function TasksView({ tasks, jobs, draft, setDraft, createTask, updateTask, runNow, loading }: { tasks: ScheduledTask[]; jobs: Job[]; draft: { title: string; prompt: string; schedule_type: string; schedule_value: string }; setDraft: (value: { title: string; prompt: string; schedule_type: string; schedule_value: string }) => void; createTask: () => void; updateTask: (task: ScheduledTask, values: Partial<ScheduledTask>) => void; runNow: (task: ScheduledTask) => void; loading: boolean }) {
  const scheduledJobs = jobs.filter((job) => job.kind === 'run_scheduled_prompt');
  return (
    <PageFrame>
      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <SectionHeader icon={Clock3} title="Create task" subtitle="Local scheduled prompts. Scheduler is off unless enabled in settings." compact />
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className="field mb-3" placeholder="Title" />
          <textarea value={draft.prompt} onChange={(event) => setDraft({ ...draft, prompt: event.target.value })} rows={6} className="field mb-3" placeholder="Prompt" />
          <select value={draft.schedule_type} onChange={(event) => setDraft({ ...draft, schedule_type: event.target.value })} className="field mb-3">
            <option value="once">once</option>
            <option value="interval">interval</option>
            <option value="cron">cron</option>
          </select>
          <input value={draft.schedule_value} onChange={(event) => setDraft({ ...draft, schedule_value: event.target.value })} className="field mb-3" placeholder="Seconds, ISO date, or cron" />
          <button onClick={createTask} className="primary-button"><Clock3 size={16} /> Create task</button>
        </Card>
        <section className="grid gap-3">
          {loading && <LoadingGrid />}
          {!loading && tasks.length === 0 && <EmptyState icon={Clock3} title="Aucune tâche" body="Crée une tâche planifiée locale pour générer des jobs internes." />}
          {!loading && tasks.map((task) => (
            <Card key={task.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-stone-100">{task.title}</div>
                  <div className="mt-1 text-sm text-zinc-500">{task.schedule_type} · {task.schedule_value || 'default'} · next {formatDate(task.next_run_at || '')}</div>
                  <p className="mt-2 line-clamp-2 text-sm text-zinc-300">{task.prompt}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone={task.enabled ? 'green' : 'slate'}>{task.enabled ? 'enabled' : 'disabled'}</Badge>
                  <button onClick={() => updateTask(task, { enabled: !task.enabled })} className="secondary-button">{task.enabled ? 'Disable' : 'Enable'}</button>
                  <button onClick={() => runNow(task)} className="secondary-button">Run now</button>
                </div>
              </div>
            </Card>
          ))}
          <Card>
            <SectionHeader icon={ListChecks} title="Scheduled job history" subtitle="Recent run_scheduled_prompt jobs." compact />
            <div className="grid gap-2">
              {scheduledJobs.slice(0, 6).map((job) => <div key={job.id} className="flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-sm"><span>{job.title}</span><Badge tone={job.status === 'succeeded' ? 'green' : job.status === 'failed' ? 'red' : 'slate'}>{job.status}</Badge></div>)}
              {scheduledJobs.length === 0 && <div className="text-sm text-zinc-600">No scheduled jobs yet</div>}
            </div>
          </Card>
        </section>
      </div>
    </PageFrame>
  );
}

function StandingOrdersView({ orders, draft, setDraft, createOrder, updateOrder, loading }: { orders: StandingOrder[]; draft: { title: string; content: string; scope: string; priority: number }; setDraft: (value: { title: string; content: string; scope: string; priority: number }) => void; createOrder: () => void; updateOrder: (order: StandingOrder, values: Partial<StandingOrder>) => void; loading: boolean }) {
  return (
    <PageFrame>
      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <SectionHeader icon={FileText} title="Create order" subtitle="Persistent user instructions injected below system policy." compact />
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className="field mb-3" placeholder="Title" />
          <textarea value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} rows={7} className="field mb-3" placeholder="Standing order" />
          <select value={draft.scope} onChange={(event) => setDraft({ ...draft, scope: event.target.value })} className="field mb-3">
            <option value="global">global</option>
            <option value="project">project</option>
            <option value="session">session</option>
          </select>
          <input type="number" value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: Number(event.target.value) })} className="field mb-3" />
          <button onClick={createOrder} className="primary-button"><FileText size={16} /> Create order</button>
        </Card>
        <section className="grid gap-3">
          {loading && <LoadingGrid />}
          {!loading && orders.length === 0 && <EmptyState icon={FileText} title="Aucun standing order" body="Ajoute des règles persistantes pour guider Omega." />}
          {!loading && orders.map((order) => (
            <Card key={order.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-stone-100">{order.title}</div>
                  <div className="mt-1 text-xs text-zinc-600">{order.scope} · priority {order.priority}</div>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">{order.content}</p>
                </div>
                <div className="flex gap-2">
                  <Badge tone={order.enabled ? 'green' : 'slate'}>{order.enabled ? 'enabled' : 'disabled'}</Badge>
                  <button onClick={() => updateOrder(order, { enabled: !order.enabled })} className="secondary-button">{order.enabled ? 'Disable' : 'Enable'}</button>
                </div>
              </div>
            </Card>
          ))}
        </section>
      </div>
    </PageFrame>
  );
}

function AgentEditor({ agent, updateAgent }: { agent: AgentProfile; updateAgent: (agent: AgentProfile, values: Partial<AgentProfile>) => void }) {
  const [draft, setDraft] = useState({
    name: agent.name,
    description: agent.description,
    system_prompt: agent.system_prompt,
    allowed_tools: agent.allowed_tools.join(', '),
    allowed_skills: agent.allowed_skills.join(', '),
    policy: JSON.stringify(agent.policy, null, 2),
  });
  useEffect(() => {
    setDraft({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      allowed_tools: agent.allowed_tools.join(', '),
      allowed_skills: agent.allowed_skills.join(', '),
      policy: JSON.stringify(agent.policy, null, 2),
    });
  }, [agent.id, agent.updated_at]);

  function save() {
    let policy: Record<string, unknown> = {};
    try {
      policy = JSON.parse(draft.policy || '{}');
    } catch {
      policy = agent.policy;
    }
    updateAgent(agent, {
      name: draft.name,
      description: draft.description,
      system_prompt: draft.system_prompt,
      allowed_tools: csv(draft.allowed_tools),
      allowed_skills: csv(draft.allowed_skills),
      policy,
    });
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-semibold text-stone-100"><Bot size={17} className="text-blue-300" /> {agent.name}</div>
          <div className="mt-1 text-xs text-zinc-600">{agent.id}{agent.builtin ? ' · builtin' : ''}</div>
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge risk={agent.risk_level} />
          <button onClick={() => updateAgent(agent, { enabled: !agent.enabled })} className="secondary-button">{agent.enabled ? 'Disable' : 'Enable'}</button>
        </div>
      </div>
      <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="field mb-3" />
      <input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="field mb-3" placeholder="Description" />
      <textarea value={draft.system_prompt} onChange={(event) => setDraft({ ...draft, system_prompt: event.target.value })} rows={5} className="field mb-3" placeholder="System prompt" />
      <div className="grid gap-3 md:grid-cols-2">
        <textarea value={draft.allowed_tools} onChange={(event) => setDraft({ ...draft, allowed_tools: event.target.value })} rows={3} className="field" placeholder="Allowed tools" />
        <textarea value={draft.allowed_skills} onChange={(event) => setDraft({ ...draft, allowed_skills: event.target.value })} rows={3} className="field" placeholder="Active skills" />
      </div>
      <pre className="mt-3 max-h-28 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{agent.allowed_tools.join(', ') || 'No tools'}</pre>
      <textarea value={draft.policy} onChange={(event) => setDraft({ ...draft, policy: event.target.value })} rows={5} className="field mt-3 font-mono text-xs" />
      <button onClick={save} className="primary-button mt-3">Save profile</button>
    </Card>
  );
}

function ToolsView({ tools, loading }: { tools: Tool[]; loading: boolean }) {
  const [query, setQuery] = useState('');
  const visibleTools = tools.filter((tool) => `${tool.name} ${tool.id} ${tool.description} ${tool.category}`.toLowerCase().includes(query.toLowerCase()));
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  if (tools.length === 0) return <PageFrame><EmptyState icon={Hammer} title="Aucun tool" body="Le registre tools est vide ou indisponible." /></PageFrame>;
  return (
    <PageFrame>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <SectionHeader icon={Hammer} title="Tools registry" subtitle="Actions exposées au runtime, avec risque et approval côté backend." compact />
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="field max-w-sm" placeholder="Rechercher un tool..." />
      </div>
      {visibleTools.length === 0 && <EmptyState icon={Hammer} title="Aucun résultat" body="Aucun tool ne correspond à cette recherche." />}
      <div className="grid gap-3 xl:grid-cols-2">
        {visibleTools.map((tool) => (
          <Card key={tool.id}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2"><TerminalSquare size={16} className="text-zinc-400" /><div className="font-semibold text-stone-100">{tool.name}</div></div>
                <div className="mt-2 text-sm leading-6 text-zinc-500">{tool.description}</div>
              </div>
              <RiskBadge risk={tool.risk_level || tool.risk} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge>{tool.category}</Badge>
              <Badge tone={tool.enabled ? 'green' : 'slate'}>{tool.enabled ? 'enabled' : 'disabled'}</Badge>
              <Badge tone={tool.requires_approval ? 'amber' : 'slate'}>{tool.requires_approval ? 'approval' : 'direct'}</Badge>
            </div>
            <pre className="mt-4 max-h-32 overflow-auto p-3 text-xs text-zinc-400">{JSON.stringify(tool.input_schema, null, 2)}</pre>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function SkillsView({ skills, draft, setDraft, createSkill, refresh, loading }: { skills: Skill[]; draft: { name: string; description: string; instructions: string }; setDraft: (value: { name: string; description: string; instructions: string }) => void; createSkill: () => void; refresh: () => void; loading: boolean }) {
  const [query, setQuery] = useState('');
  const visibleSkills = skills.filter((skill) => `${skill.name} ${skill.description} ${skill.risk_level}`.toLowerCase().includes(query.toLowerCase()));
  async function toggle(skill: Skill) {
    await api(`/api/skills/${skill.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !skill.enabled }) });
    refresh();
  }
  return (
    <PageFrame>
      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <SectionHeader icon={Sparkles} title="Create skill" subtitle="Instructions locales, contrôlées par le registre backend." compact />
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="field mb-3" placeholder="skill-name" />
          <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} className="field mb-3" placeholder="Description" />
          <textarea value={draft.instructions} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} rows={8} className="field mb-3" placeholder="Markdown instructions" />
          <button onClick={createSkill} className="primary-button">Create</button>
        </Card>
        <section className="grid gap-3">
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="field" placeholder="Rechercher une skill..." />
          {loading && <LoadingGrid />}
          {!loading && visibleSkills.length === 0 && <EmptyState icon={Sparkles} title="Aucune skill" body="Crée une skill locale pour enrichir le contexte Omega." />}
          {!loading && visibleSkills.map((skill) => (
            <Card key={skill.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-stone-100">{skill.name}</div>
                  <p className="mt-1 text-sm text-zinc-500">{skill.description || 'Aucune description.'}</p>
                </div>
                <button onClick={() => toggle(skill)} className="secondary-button">{skill.enabled ? 'Disable' : 'Enable'} · {skill.risk_level}</button>
              </div>
              <pre className="mt-3 max-h-44 overflow-auto p-3 text-xs text-zinc-400">{skill.instructions}</pre>
            </Card>
          ))}
        </section>
      </div>
    </PageFrame>
  );
}

function PluginsView({ plugins, setPluginEnabled, rescanPlugins, loading }: { plugins: Plugin[]; setPluginEnabled: (plugin: Plugin, enabled: boolean) => void; rescanPlugins: () => void; loading: boolean }) {
  const [query, setQuery] = useState('');
  const visiblePlugins = plugins.filter((plugin) => `${plugin.name} ${plugin.id} ${plugin.description} ${plugin.trust_level} ${plugin.status}`.toLowerCase().includes(query.toLowerCase()));
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  return (
    <PageFrame>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <SectionHeader icon={Plug} title="Plugin review" subtitle="Manifest-only plugins. No external plugin code is executed in v0.1." compact />
        <div className="flex flex-wrap gap-2">
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="field max-w-xs" placeholder="Rechercher un plugin..." />
          <button onClick={rescanPlugins} className="secondary-button">Rescan</button>
        </div>
      </div>
      {visiblePlugins.length === 0 && <EmptyState icon={Plug} title="Aucun plugin" body="Les plugins v0.1 sont manifest-only et apparaitront ici." />}
      <div className="grid gap-3 xl:grid-cols-2">
        {visiblePlugins.map((plugin) => (
          <Card key={plugin.path}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold text-stone-100">{plugin.name}</div>
                <div className="mt-1 text-xs text-zinc-600">{plugin.id} · {plugin.version} · {plugin.status}</div>
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <Badge tone={plugin.trust_level === 'blocked' ? 'red' : plugin.trust_level === 'untrusted' ? 'amber' : plugin.trust_level === 'local' ? 'cyan' : 'green'}>{plugin.trust_level}</Badge>
                <Badge tone={plugin.enabled ? 'green' : 'slate'}>{plugin.enabled ? 'enabled' : 'disabled'}</Badge>
                <Badge tone={plugin.security_review?.risk_level === 'critical' ? 'red' : plugin.security_review?.risk_level === 'high' ? 'amber' : 'slate'}>{plugin.security_review?.risk_level || 'unknown'}</Badge>
              </div>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-500">{plugin.description || 'Manifest loaded only.'}</p>
            {plugin.error && <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{plugin.error}</div>}
            {(plugin.security_review?.critical_warnings || []).map((warning) => <div key={warning} className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">{warning}</div>)}
            {(plugin.security_review?.warnings || []).map((warning) => <div key={warning} className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">{warning}</div>)}
            <div className="mt-4">
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-zinc-600">Permissions</div>
              <div className="flex flex-wrap gap-2">
                {(plugin.permissions || []).length === 0 && <Badge>none</Badge>}
                {(plugin.permissions || []).map((permission) => <Badge key={permission} tone={permission === 'shell.execute' ? 'red' : permission.includes('write') || permission.includes('control') || permission.includes('network') ? 'amber' : 'slate'}>{permission}</Badge>)}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={() => setPluginEnabled(plugin, !plugin.enabled)} disabled={plugin.status !== 'loaded' || plugin.trust_level === 'blocked'} className="secondary-button disabled:cursor-not-allowed disabled:opacity-50">{plugin.enabled ? 'Disable' : 'Enable'}</button>
            </div>
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-zinc-300">Raw manifest</summary>
              <pre className="mt-3 max-h-56 overflow-auto p-3 text-xs text-zinc-400">{JSON.stringify(plugin.raw_manifest || plugin.declares, null, 2)}</pre>
            </details>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function SecurityView({ report, severity, setSeverity, runAudit, applyFixes, loading }: { report: SecurityReport | null; severity: string; setSeverity: (value: string) => void; runAudit: () => void; applyFixes: () => void; loading: boolean }) {
  if (loading || !report) return <PageFrame><LoadingGrid /></PageFrame>;
  const findings = severity === 'all' ? report.findings : report.findings.filter((item) => item.severity === severity);
  const criticalOrHigh = report.findings.filter((item) => item.severity === 'critical' || item.severity === 'high').length;
  return (
    <PageFrame>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <SectionHeader icon={Shield} title="Security audit" subtitle="Local Omega configuration, tools, plugins, channels and automation posture." compact />
        <div className="flex flex-wrap gap-2">
          <button onClick={runAudit} className="secondary-button">Run audit</button>
          <button onClick={applyFixes} className="primary-button">Apply safe fixes</button>
        </div>
      </div>
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <Card><div className="text-sm text-zinc-600">Score</div><div className="mt-1 text-3xl font-semibold text-stone-100">{report.score}</div></Card>
        <Card><div className="text-sm text-zinc-600">High/Critical</div><div className="mt-1 text-3xl font-semibold text-stone-100">{criticalOrHigh}</div></Card>
        <Card><div className="text-sm text-zinc-600">Generated</div><div className="mt-2 text-sm text-zinc-300">{formatDate(report.generated_at)}</div></Card>
      </div>
      {(report.fixed || []).length > 0 && <div className="mb-4 rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3 text-sm text-emerald-100">{report.fixed?.join(' ')}</div>}
      <div className="mb-4 flex flex-wrap gap-2">
        {['all', 'critical', 'high', 'medium', 'low', 'info'].map((item) => (
          <button key={item} onClick={() => setSeverity(item)} className={severity === item ? 'primary-button' : 'secondary-button'}>{item}</button>
        ))}
      </div>
      <div className="grid gap-3">
        {findings.map((finding, index) => (
          <Card key={`${finding.area}-${index}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-stone-100">{finding.area}</div>
                <p className="mt-2 text-sm leading-6 text-zinc-300">{finding.finding}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={finding.severity === 'critical' ? 'red' : finding.severity === 'high' ? 'red' : finding.severity === 'medium' ? 'amber' : finding.severity === 'low' ? 'cyan' : 'green'}>{finding.severity}</Badge>
                {finding.auto_fix_available && <Badge tone="green">safe fix</Badge>}
              </div>
            </div>
            <div className="mt-3 rounded-xl bg-white/[0.03] p-3 text-sm text-zinc-500">{finding.recommendation}</div>
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function ApprovalsView({ approvals, resolveApproval, loading }: { approvals: Approval[]; resolveApproval: (id: string, approve: boolean) => void; loading: boolean }) {
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  if (approvals.length === 0) return <PageFrame><EmptyState icon={ShieldAlert} title="Aucune approval" body="Les actions sensibles à valider apparaîtront ici." /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={ShieldAlert} title="Approvals" subtitle="Actions sensibles en attente de décision explicite." />
      <div className="grid gap-3">
        {approvals.map((approval) => (
          <Card key={approval.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-stone-100">{approval.tool_name || approval.action}</div>
                <div className="mt-1 text-sm text-zinc-500">{approval.reason || 'Action sensible.'}</div>
                <div className="mt-2 text-xs text-zinc-600">{formatDate(approval.created_at)}</div>
              </div>
              <div className="flex items-center gap-2"><RiskBadge risk={approval.risk_level} /><Badge>{approval.status}</Badge></div>
            </div>
            <pre className="mt-3 max-h-40 overflow-auto p-3 text-xs text-zinc-400">{JSON.stringify(approval.arguments, null, 2)}</pre>
            {approval.status === 'pending' && <div className="mt-3 flex gap-2"><button onClick={() => resolveApproval(approval.id, true)} className="primary-button"><CheckCircle2 size={16} /> Approuver</button><button onClick={() => resolveApproval(approval.id, false)} className="danger-button"><XCircle size={16} /> Refuser</button></div>}
          </Card>
        ))}
      </div>
    </PageFrame>
  );
}

function JobsView({ jobs, jobKind, setJobKind, createJob, loading }: { jobs: Job[]; jobKind: string; setJobKind: (value: string) => void; createJob: () => void; loading: boolean }) {
  return (
    <PageFrame>
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <select value={jobKind} onChange={(e) => setJobKind(e.target.value)} className="field max-w-xs">
            <option value="scan_workspace">scan_workspace</option>
            <option value="summarize_session">summarize_session</option>
            <option value="memory_compaction">memory_compaction</option>
          </select>
          <button onClick={createJob} className="primary-button"><ListChecks size={16} /> Create job</button>
        </div>
      </Card>
      <div className="mt-4 grid gap-3">
        {loading && <LoadingGrid />}
        {!loading && jobs.length === 0 && <EmptyState icon={ListChecks} title="Aucun job" body="Crée un job interne pour scanner, résumer ou compacter." />}
        {!loading && jobs.map((job) => <JobCard key={job.id} job={job} />)}
      </div>
    </PageFrame>
  );
}

function JobCard({ job }: { job: Job }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-stone-100">{job.title}</div>
          <div className="mt-1 text-sm text-zinc-500">{job.kind} · {formatDate(job.updated_at)}</div>
        </div>
        <Badge tone={job.status === 'succeeded' ? 'green' : job.status === 'failed' ? 'red' : job.status === 'running' ? 'cyan' : 'slate'}>{job.status}</Badge>
      </div>
      <pre className="mt-3 max-h-36 overflow-auto rounded-xl bg-black/20 p-3 text-xs text-zinc-500">{job.output_json}</pre>
    </Card>
  );
}

function MemoryView({ memory, draft, setDraft, createMemory, refresh, loading }: { memory: Memory[]; draft: { key: string; content: string; tags: string }; setDraft: (value: { key: string; content: string; tags: string }) => void; createMemory: () => void; refresh: () => void; loading: boolean }) {
  async function remove(id: string) {
    await api(`/api/memory/${id}`, { method: 'DELETE' });
    refresh();
  }
  return (
    <PageFrame>
      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <SectionHeader icon={Database} title="Create memory" subtitle="Mémoires locales consultables par le runtime." compact />
          <input value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} className="field mb-3" placeholder="Key" />
          <textarea value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })} rows={6} className="field mb-3" placeholder="Content" />
          <input value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} className="field mb-3" placeholder="tags, comma, separated" />
          <button onClick={createMemory} className="primary-button">Remember</button>
        </Card>
        <section className="grid gap-3">
          {loading && <LoadingGrid />}
          {!loading && memory.length === 0 && <EmptyState icon={Database} title="Aucune mémoire" body="Les préférences et faits persistants seront listés ici." />}
          {!loading && memory.map((item) => (
            <Card key={item.id}>
              <div className="flex justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-stone-100">{item.key}</div>
                  <p className="mt-1 text-sm leading-6 text-zinc-300">{item.content}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-600"><Badge>{item.scope}</Badge>{item.tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}</div>
                </div>
                <button onClick={() => remove(item.id)} className="grid h-9 w-9 place-items-center rounded-2xl border border-white/10 text-zinc-500 transition hover:border-red-400/30 hover:text-red-300" aria-label="Delete memory"><Trash2 size={16} /></button>
              </div>
            </Card>
          ))}
        </section>
      </div>
    </PageFrame>
  );
}

function LogsView({ logs, loading }: { logs: EventItem[]; loading: boolean }) {
  if (loading) return <PageFrame><LoadingGrid /></PageFrame>;
  if (logs.length === 0) return <PageFrame><EmptyState icon={ScrollText} title="Aucun log" body="Les événements runtime et audit apparaîtront ici." /></PageFrame>;
  return (
    <PageFrame>
      <SectionHeader icon={History} title="Audit timeline" subtitle="Événements, approvals, tools et logs redacted." />
      <div className="relative ml-3 border-l border-white/10 pl-6">
        {logs.map((log, index) => (
          <div key={log.id || `${log.ts}-${index}`} className="relative mb-4">
            <div className="absolute -left-[31px] top-2 h-3 w-3 rounded-full border border-white/15 bg-zinc-500" />
            <Card>
              <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-zinc-500">
                <FileText size={15} />
                <span className="font-medium text-zinc-200">{log.type || log.action || 'log'}</span>
                <span>·</span>
                <span>{formatDate(log.created_at || log.ts || '')}</span>
              </div>
              <pre className="max-h-52 overflow-auto p-3 text-xs text-zinc-400">{JSON.stringify(log.payload || log, null, 2)}</pre>
            </Card>
          </div>
        ))}
      </div>
    </PageFrame>
  );
}

function SettingsView({ status, settingsData, performanceTraces, reloadRegistries, patchSettings, loading }: { status: Status | null; settingsData: SettingsData; performanceTraces: PerformanceTrace[]; reloadRegistries: () => void; patchSettings: (values: Record<string, unknown>) => void; loading: boolean }) {
  const workspaceFullAccess = Boolean(settingsData.workspace_full_access ?? status?.workspace_full_access);
  const allowDelete = Boolean(settingsData.allow_delete_in_workspace ?? status?.allow_delete_in_workspace);
  const allowShell = Boolean(settingsData.shell_full_access_in_workspace ?? status?.shell_full_access_in_workspace);
  const requireInsideApproval = Boolean(settingsData.require_approvals ?? true);
  const sections: Array<[string, Array<[string, React.ReactNode, React.ElementType]>]> = [
    ['Général', [['Workspace', settingsData.workspace || status?.workspace || '...', HardDrive], ['Theme', settingsData.theme || status?.gateway.theme || 'dark', Settings]]],
    ['Modèle', [['Provider', settingsData.provider || status?.provider || 'codex', Cpu], ['Model', settingsData.model || status?.model || 'gpt-5.5', Zap]]],
    ['Gateway', [['Endpoint', `${settingsData.host || status?.gateway.host}:${settingsData.port || status?.gateway.port}`, Activity], ['Open browser', String(settingsData.open_browser ?? status?.gateway.open_browser), Gauge]]],
    ['Sécurité', [['Safe mode', String(settingsData.safe_mode ?? status?.safe_mode), Shield], ['Require approvals', String(settingsData.require_approvals ?? true), ShieldAlert]]],
    ['Workspace permissions', [['Workspace Full Access', String(workspaceFullAccess), Shield], ['Shell in workspace', String(allowShell), TerminalSquare], ['Delete in workspace', String(allowDelete), Trash2], ['Outside workspace', 'denied', ShieldAlert]]],
    ['Performance', [['Fast mode', String(status?.fast_mode ?? true), Gauge], ['Reasoning', status?.reasoning_detail || 'minimal', Sparkles], ['Streaming', String(status?.streaming ?? true), Activity], ['Perf logging', String(status?.perf_logging ?? true), ScrollText]]],
    ['Expérimental', [['Scheduler', String(settingsData.scheduler_enabled ?? false), Clock3], ['Scheduler tick', `${settingsData.scheduler_tick_seconds ?? 30}s`, Gauge]]],
  ];
  return (
    <PageFrame>
      {loading && <LoadingGrid />}
      <SectionHeader icon={Settings} title="Settings" subtitle="Configuration locale exposée par Omega Gateway." />
      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map(([section, rows]) => (
          <Card key={section}>
            <div className="mb-4 text-sm font-semibold text-stone-100">{section}</div>
            <div className="grid gap-3">
              {rows.map(([label, value, Icon]) => (
                <div key={label} className="flex items-start gap-3 rounded-2xl border border-white/10 bg-black/10 p-3">
                  <Avatar icon={Icon} tone="slate" />
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-500">{label}</div>
                    <div className="mt-1 break-words font-medium text-stone-100">{value}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
      <Card>
        <SectionHeader icon={Shield} title="Workspace permissions" subtitle="Omega peut modifier librement les fichiers dans ce workspace. Les accès hors workspace restent bloqués." compact />
        <div className="mb-4 rounded-2xl border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">
          Workspace Full Access donne à Omega un accès direct aux fichiers et commandes dans le workspace configuré. Les chemins hors workspace, secrets et emplacements système restent refusés par le backend.
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <ToggleRow label="Workspace Full Access" value={workspaceFullAccess} onToggle={() => patchSettings({ workspace_full_access: !workspaceFullAccess })} />
          <ToggleRow label="Allow delete in workspace" value={allowDelete} onToggle={() => patchSettings({ allow_delete_in_workspace: !allowDelete })} />
          <ToggleRow label="Allow shell in workspace" value={allowShell} onToggle={() => patchSettings({ shell_full_access_in_workspace: !allowShell })} />
          <ToggleRow label="Require approval inside workspace" value={requireInsideApproval} onToggle={() => patchSettings({ require_approvals: !requireInsideApproval })} />
        </div>
      </Card>
      <Card>
        <SectionHeader icon={Shield} title="Runtime controls" subtitle="Ces réglages passent par validation backend." compact />
        <div className="flex flex-wrap gap-3">
          <button onClick={() => patchSettings({ open_browser: !(settingsData.open_browser ?? status?.gateway.open_browser) })} className="secondary-button">Toggle open browser</button>
          <button onClick={() => patchSettings({ safe_mode: !(settingsData.safe_mode ?? status?.safe_mode) })} className="secondary-button">Toggle safe mode</button>
          <button onClick={() => patchSettings({ require_approvals: !(settingsData.require_approvals ?? true) })} className="secondary-button">Toggle approvals</button>
          <button onClick={reloadRegistries} className="secondary-button"><RefreshCw size={16} /> Reload registries</button>
        </div>
      </Card>
      <Card>
        <SectionHeader icon={Activity} title="Performance récente" subtitle="Dernières traces de chat mesurées côté gateway." compact />
        {performanceTraces.length === 0 && <div className="text-sm text-zinc-500">Aucune trace de chat récente.</div>}
        <div className="grid gap-2">
          {performanceTraces.slice(0, 6).map((trace) => (
            <div key={trace.trace_id} className="rounded-2xl border border-white/10 bg-black/10 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
                <span>{formatDate(trace.created_at)}</span>
                <Badge tone={trace.failed ? 'red' : trace.completed ? 'green' : 'amber'}>{formatDurationMs(trace.steps_ms.total_duration || 0)}</Badge>
              </div>
              <div className="grid gap-1 text-xs text-zinc-500 sm:grid-cols-2">
                {Object.entries(trace.steps_ms).slice(0, 8).map(([step, value]) => (
                  <div key={step} className="flex justify-between gap-3 rounded-xl bg-white/[0.035] px-2.5 py-1.5">
                    <span className="truncate">{step}</span>
                    <span className="text-zinc-300">{formatDurationMs(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </PageFrame>
  );
}

function ToggleRow({ label, value, onToggle }: { label: string; value: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/10 p-3 text-left transition hover:bg-white/[0.045] focus:outline-none focus:ring-2 focus:ring-blue-300/30">
      <span className="text-sm font-medium text-stone-100">{label}</span>
      <span className={`h-6 w-11 rounded-full border p-0.5 transition ${value ? 'border-blue-300/30 bg-blue-500/40' : 'border-white/10 bg-white/[0.04]'}`}>
        <span className={`block h-5 w-5 rounded-full bg-stone-100 transition ${value ? 'translate-x-5' : 'translate-x-0'}`} />
      </span>
    </button>
  );
}

function RuntimeRail({ status, tools, skills, approvals, jobs }: { status: Status | null; tools: Tool[]; skills: Skill[]; approvals: Approval[]; jobs: Job[] }) {
  const activeTools = tools.filter((tool) => tool.enabled).length || status?.tools_count || 0;
  const activeSkills = skills.filter((skill) => skill.enabled).length || status?.skills_count || 0;
  const runningJobs = jobs.filter((job) => job.status === 'running').length;
  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-4 flex items-center gap-2 font-semibold text-stone-100"><LayoutDashboard size={17} className="text-blue-300" /> Runtime status</div>
        <div className="grid gap-3 text-sm">
          <MetricRow label="Gateway" value={`${status?.gateway.host || '127.0.0.1'}:${status?.gateway.port || '8765'}`} icon={Activity} />
          <MetricRow label="Provider" value={status?.provider || '...'} icon={Cpu} />
          <MetricRow label="Model" value={status?.model || '...'} icon={Zap} />
          <MetricRow label="Codex" value={status?.auth_codex.connected ? 'connected' : 'disconnected'} icon={Shield} tone={status?.auth_codex.connected ? 'green' : 'amber'} />
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-3">
        <RuntimeCard icon={Hammer} label="Tools" value={activeTools} />
        <RuntimeCard icon={Sparkles} label="Skills" value={activeSkills} />
        <RuntimeCard icon={ShieldAlert} label="Approvals" value={approvals.length} tone={approvals.length ? 'amber' : 'slate'} />
        <RuntimeCard icon={ListChecks} label="Jobs" value={runningJobs} tone={runningJobs ? 'cyan' : 'slate'} />
      </div>
      <Card>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-stone-100"><Archive size={16} className="text-emerald-200" /> Local safety</div>
        <div className="space-y-2 text-xs leading-5 text-zinc-500">
          <div>Workspace scoped filesystem</div>
          <div>Approval engine for sensitive tools</div>
          <div>Manifest-only plugins</div>
          <div>Redacted audit logs</div>
        </div>
      </Card>
    </div>
  );
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-6xl space-y-5 p-6 max-sm:p-4">{children}</div>;
}

function Card({ children, interactive = false }: { children: React.ReactNode; interactive?: boolean }) {
  return <article className={`rounded-3xl border border-white/10 bg-[var(--omega-card)] p-4 shadow-soft ${interactive ? 'transition hover:border-white/15 hover:bg-[var(--omega-card-hover)]' : ''}`}>{children}</article>;
}

function Badge({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'cyan' | 'green' | 'amber' | 'red' | 'violet' }) {
  const tones = {
    slate: 'border-white/10 bg-white/[0.045] text-zinc-300',
    cyan: 'border-blue-400/20 bg-blue-500/10 text-blue-100',
    green: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100',
    amber: 'border-amber-400/20 bg-amber-400/10 text-amber-100',
    red: 'border-red-400/20 bg-red-500/10 text-red-100',
    violet: 'border-violet-400/15 bg-violet-400/8 text-violet-200',
  }[tone];
  return <span className={`inline-flex h-6 items-center rounded-full border px-2 text-[11px] font-medium ${tones}`}>{children}</span>;
}

function RiskBadge({ risk }: { risk: string }) {
  const tone = risk === 'critical' ? 'red' : risk === 'high' ? 'amber' : risk === 'medium' ? 'violet' : 'green';
  return <Badge tone={tone}>{risk || 'low'}</Badge>;
}

function StatusPill({ icon: Icon, label, tone }: { icon: React.ElementType; label: string; tone: 'slate' | 'cyan' | 'green' | 'amber' | 'violet' }) {
  return <span className={`inline-flex h-9 items-center gap-2 rounded-full border px-3 text-xs font-medium ${toneClass(tone)}`}><Icon size={15} /> {label}</span>;
}

function Avatar({ icon: Icon, tone }: { icon: React.ElementType; tone: 'cyan' | 'amber' | 'slate' }) {
  const styles = tone === 'cyan' ? 'border-blue-400/20 bg-blue-500/10 text-blue-100' : tone === 'amber' ? 'border-amber-400/20 bg-amber-400/10 text-amber-100' : 'border-white/10 bg-white/[0.045] text-zinc-300';
  return <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-2xl border ${styles}`}><Icon size={17} /></div>;
}

function SectionHeader({ icon: Icon, title, subtitle, compact = false }: { icon: React.ElementType; title: string; subtitle: string; compact?: boolean }) {
  return (
    <div className={compact ? 'mb-4' : 'mb-5'}>
      <div className="flex items-center gap-2 font-semibold text-stone-100"><Icon size={18} className="text-zinc-400" /> {title}</div>
      <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
    </div>
  );
}

function ChatEmptyState({ setInput }: { setInput: (value: string) => void }) {
  const suggestions = [
    { label: 'Explorer mon workspace', prompt: 'Explore mon workspace et propose-moi un résumé utile.', icon: HardDrive },
    { label: 'Créer une skill', prompt: 'Aide-moi à créer une skill Omega utile.', icon: Sparkles },
    { label: 'Vérifier la sécurité d’Omega', prompt: 'Vérifie la sécurité d’Omega et signale les points importants.', icon: Shield },
  ];
  return (
    <div className="flex min-h-[46vh] flex-col items-center justify-center text-center">
      <div className="mb-6 grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.045] text-zinc-200 shadow-inset-line">
        <Bot size={22} />
      </div>
      <h2 className="text-3xl font-semibold tracking-tight text-stone-100 max-sm:text-2xl">Comment puis-je t’aider aujourd’hui ?</h2>
      <div className="mt-8 grid w-full gap-3 sm:grid-cols-3">
        {suggestions.map(({ label, prompt, icon: Icon }) => (
          <button key={label} onClick={() => setInput(prompt)} className="group flex min-h-24 flex-col items-start justify-between rounded-[22px] border border-white/10 bg-white/[0.035] p-4 text-left text-sm text-stone-200 transition hover:border-white/15 hover:bg-white/[0.055] focus:outline-none focus:ring-2 focus:ring-blue-300/30">
            <Icon size={18} className="text-zinc-500 transition group-hover:text-zinc-300" />
            <span className="leading-5">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, body }: { icon: React.ElementType; title: string; body: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-white/12 bg-white/[0.03] p-10 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.045] text-zinc-300"><Icon size={22} /></div>
      <div className="font-semibold text-stone-100">{title}</div>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-500">{body}</p>
    </div>
  );
}

function LoadingGrid() {
  return <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-3xl border border-white/10 bg-white/[0.035]" />)}</div>;
}

function ThinkingIndicator({ events = [] }: { events?: ReasoningEvent[] }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-300">
      <div className="flex items-center gap-3"><Loader2 size={16} className="animate-spin" /> Omega réfléchit...</div>
      {events.length > 0 && <ReasoningPanel events={events} />}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="border-b border-red-400/20 bg-red-500/10 px-6 py-3 text-sm text-red-100"><div className="flex items-center gap-2"><AlertTriangle size={16} /> {message}</div></div>;
}

function RuntimeCard({ icon: Icon, label, value, tone = 'slate' }: { icon: React.ElementType; label: string; value: number; tone?: 'slate' | 'cyan' | 'amber' }) {
  return <div className={`rounded-3xl border p-3 ${toneClass(tone)}`}><Icon size={16} /><div className="mt-3 text-2xl font-semibold">{value}</div><div className="text-xs opacity-75">{label}</div></div>;
}

function MetricRow({ icon: Icon, label, value, tone = 'slate' }: { icon: React.ElementType; label: string; value: string; tone?: 'slate' | 'green' | 'amber' }) {
  return <div className="flex items-center gap-3"><Icon size={15} className={tone === 'green' ? 'text-emerald-200' : tone === 'amber' ? 'text-amber-200' : 'text-zinc-500'} /><div className="min-w-0"><div className="text-xs text-zinc-600">{label}</div><div className="truncate text-zinc-200">{value}</div></div></div>;
}

function AppShellSkeleton() {
  return (
    <div className="grid min-h-screen grid-cols-[260px_minmax(0,1fr)] bg-[var(--omega-bg)] p-4 text-stone-100 max-md:grid-cols-1">
      <div className="rounded-3xl border border-white/10 bg-white/[0.035]" />
      <div className="mx-4 rounded-3xl border border-white/10 bg-white/[0.03] p-6"><LoadingGrid /></div>
    </div>
  );
}

function toneClass(tone: 'slate' | 'cyan' | 'green' | 'amber' | 'red' | 'violet') {
  const tones = {
    slate: 'border-white/10 bg-white/[0.045] text-zinc-300',
    cyan: 'border-blue-400/20 bg-blue-500/10 text-blue-100',
    green: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100',
    amber: 'border-amber-400/20 bg-amber-400/10 text-amber-100',
    red: 'border-red-400/20 bg-red-500/10 text-red-100',
    violet: 'border-violet-400/15 bg-violet-400/8 text-violet-200',
  };
  return tones[tone];
}

function parseWsEvent(value: string): WsEvent | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed as WsEvent;
  } catch {
    return null;
  }
}

function isReasoningWsEvent(event: WsEvent) {
  const type = event.type || '';
  const payloadType = String(event.payload?.reasoning_type || event.payload?.type || '');
  return type.startsWith('reasoning.') || type.startsWith('tool.') || type.startsWith('approval.') || payloadType.startsWith('reasoning.');
}

function normalizeReasoningEvent(event: WsEvent): ReasoningEvent | null {
  const payload = event.payload || {};
  const id = String(payload.id || '');
  const sessionId = String(payload.session_id || event.session_id || '');
  const type = String(payload.reasoning_type || payload.type || event.type || '');
  if (!id || !sessionId || !type) return null;
  return {
    id,
    session_id: sessionId,
    message_id: typeof payload.message_id === 'string' ? payload.message_id : event.message_id || null,
    type,
    title: String(payload.title || type),
    content: String(payload.content || ''),
    status: isReasoningStatus(payload.status) ? payload.status : 'completed',
    visibility: isReasoningVisibility(payload.visibility) ? payload.visibility : 'public',
    created_at: String(payload.created_at || new Date().toISOString()),
    metadata: typeof payload.metadata === 'object' && payload.metadata !== null ? payload.metadata as Record<string, unknown> : {},
    metadata_json: typeof payload.metadata_json === 'string' ? payload.metadata_json : undefined,
  };
}

function mergeReasoningEvents(current: ReasoningEvent[], incoming: ReasoningEvent[]) {
  const byId = new Map<string, ReasoningEvent>();
  for (const event of current) byId.set(event.id, event);
  for (const event of incoming) byId.set(event.id, event);
  return Array.from(byId.values()).sort((left, right) => left.created_at.localeCompare(right.created_at));
}

function mergeEvents(current: EventItem[], incoming: EventItem[]) {
  const byId = new Map<string, EventItem>();
  for (const event of current) byId.set(event.id || `${event.type}-${event.created_at}`, event);
  for (const event of incoming) byId.set(event.id || `${event.type}-${event.created_at}`, event);
  return Array.from(byId.values()).sort((left, right) => String(right.created_at || right.ts || '').localeCompare(String(left.created_at || left.ts || '')));
}

function loadRecentModelRefs() {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem('omega.recentModels') || '[]');
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string').slice(0, 6) : [];
  } catch {
    return [];
  }
}

function rememberModelRef(modelRef: string, setRecentModelRefs: React.Dispatch<React.SetStateAction<string[]>>) {
  setRecentModelRefs((current) => {
    const next = [modelRef, ...current.filter((item) => item !== modelRef)].slice(0, 6);
    try {
      window.localStorage.setItem('omega.recentModels', JSON.stringify(next));
    } catch {
      // localStorage can be unavailable in private contexts.
    }
    return next;
  });
}

function attachLatestUserMessageId(messages: Message[], messageId: string) {
  if (!messageId || messages.some((message) => message.id === messageId)) return messages;
  const next = [...messages];
  for (let index = next.length - 1; index >= 0; index -= 1) {
    if (next[index].role === 'user' && !next[index].id) {
      next[index] = { ...next[index], id: messageId };
      break;
    }
  }
  return next;
}

function isReasoningStatus(value: unknown): value is ReasoningEvent['status'] {
  return value === 'pending' || value === 'running' || value === 'completed' || value === 'failed';
}

function isReasoningVisibility(value: unknown): value is ReasoningEvent['visibility'] {
  return value === 'public' || value === 'internal' || value === 'redacted';
}

function formatDate(value: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

function formatDurationMs(value: number) {
  if (!Number.isFinite(value)) return '';
  if (value < 1000) return `${Math.max(0, Math.round(value))} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
}

function stringifyCompact(value: unknown) {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function csv(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function projectName(projects: Project[], projectId?: string | null) {
  return projects.find((project) => project.id === projectId)?.name || 'Default Workspace';
}

function errorMessage(value: unknown) {
  return value instanceof Error ? value.message : String(value);
}



