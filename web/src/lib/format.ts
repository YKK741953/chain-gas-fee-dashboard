export function formatTimestamp(seconds?: number): string {
  if (!seconds) return '—';
  const date = new Date(seconds * 1000);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatSince(seconds?: number): string {
  if (!seconds) return 'unknown';
  const deltaMs = Date.now() - seconds * 1000;
  if (deltaMs < 0) return 'moments ago';
  const deltaSeconds = Math.floor(deltaMs / 1000);
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  const minutes = Math.floor(deltaSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function formatMode(mode?: string): string {
  if (!mode) return 'unknown';
  return mode.replace('-', ' ');
}
