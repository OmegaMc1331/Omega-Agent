import { reconnectDelay } from './reconnect';
import type { EventConnectionStatus, EventMessage, OmegaEvent } from './eventTypes';

type EventHandler = (event: OmegaEvent) => void;
type StatusHandler = (status: EventConnectionStatus) => void;

const LAST_EVENT_KEY = 'omega.last_event_id';

export class OmegaEventClient {
  private socket: WebSocket | null = null;
  private closed = false;
  private attempt = 0;
  private handlers = new Set<EventHandler>();
  private statusHandlers = new Set<StatusHandler>();

  constructor(private readonly path = '/ws') {}

  connect() {
    this.closed = false;
    this.setStatus(this.attempt > 0 ? 'reconnecting' : 'connecting');
    const lastId = safeLocalStorageGet(LAST_EVENT_KEY);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = new URL(this.path, `${protocol}//${window.location.host}`);
    if (lastId) url.searchParams.set('last_event_id', lastId);
    this.socket = new WebSocket(url);
    this.socket.onopen = () => {
      this.attempt = 0;
      this.setStatus('connected');
    };
    this.socket.onmessage = (message) => this.handleMessage(message);
    this.socket.onclose = () => {
      if (this.closed) {
        this.setStatus('closed');
        return;
      }
      this.setStatus('reconnecting');
      const delay = reconnectDelay(this.attempt++);
      window.setTimeout(() => this.connect(), delay);
    };
    this.socket.onerror = () => this.socket?.close();
  }

  close() {
    this.closed = true;
    this.socket?.close();
    this.socket = null;
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  replay(lastEventId?: string) {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify({ type: 'events.replay', last_event_id: lastEventId || safeLocalStorageGet(LAST_EVENT_KEY) }));
  }

  private handleMessage(message: MessageEvent) {
    try {
      const parsed = JSON.parse(String(message.data)) as EventMessage;
      const event = normalizeEvent(parsed);
      if (!event) return;
      safeLocalStorageSet(LAST_EVENT_KEY, event.id);
      this.handlers.forEach((handler) => handler(event));
    } catch {
      // Ignore malformed websocket frames.
    }
  }

  private setStatus(status: EventConnectionStatus) {
    this.statusHandlers.forEach((handler) => handler(status));
  }
}

export function normalizeEvent(message: EventMessage): OmegaEvent | null {
  const event = message.event || message;
  const id = event.id || event.event_id;
  if (!id || !event.type || !event.version) return null;
  return {
    id,
    event_id: id,
    version: event.version,
    type: event.type,
    timestamp: event.timestamp,
    session_id: event.session_id,
    run_id: event.run_id,
    step_id: event.step_id,
    user_id: event.user_id,
    source: event.source,
    level: event.level,
    visibility: event.visibility,
    payload: event.payload || {},
    metadata: event.metadata || {},
  };
}

function safeLocalStorageGet(key: string): string {
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function safeLocalStorageSet(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // localStorage can be unavailable in private contexts.
  }
}
