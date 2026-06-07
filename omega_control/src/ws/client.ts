export function createOmegaSocket(onMessage: (event: MessageEvent) => void) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
  socket.onmessage = onMessage;
  return socket;
}
