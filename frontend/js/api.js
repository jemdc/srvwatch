/**
 * SRVWatch — Central API client
 * All fetch calls to the central server go through here.
 */

const API_BASE = window.SRVWATCH_API_BASE || "";   // same-origin by default

async function apiFetch(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, options);
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return resp.json();
}

export const api = {
  /** List all configured servers with online status */
  servers: () => apiFetch("/api/servers"),

  /** Latest live snapshot for one server */
  live: (serverId) => apiFetch(`/api/servers/${serverId}/live`),

  /** Historical time-bucketed data */
  history: (serverId, range = "1h", gpuIndex = -1) =>
    apiFetch(`/api/servers/${serverId}/history?range=${range}&gpu_index=${gpuIndex}`),

  /** GPU list for a server */
  gpus: (serverId) => apiFetch(`/api/servers/${serverId}/gpus`),

  /** Health check */
  health: () => apiFetch("/api/health"),
};
