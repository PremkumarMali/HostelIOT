// Thin wrapper around the backend REST API (same origin: Vite / nginx proxy to :8000).

async function request(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = typeof body.detail === 'string' ? body.detail : res.statusText
    throw Object.assign(new Error(message), { status: res.status })
  }
  return body
}

const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  roomHistory: (room) => request(`/api/rooms/${encodeURIComponent(room)}/history`),
  waterHistory: () => request('/api/water/history'),
  coldHistory: (unit) => request(`/api/cold-chain/${encodeURIComponent(unit)}/history`),
  ack: (id) => post(`/api/alerts/${encodeURIComponent(id)}/ack`, { by: 'Dashboard' }),

  // Demo-mode fault simulator (404 when DEMO_MODE=false, 503 when the simulator is down)
  simStatus: () => request('/api/sim/status'),
  injectFault: (type) => post('/api/sim/faults', { type }),
  clearFaults: (target) => post('/api/sim/clear', target ? { target } : {}),
  togglePause: () => post('/api/sim/pause'),
}
