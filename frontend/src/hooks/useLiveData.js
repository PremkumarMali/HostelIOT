// Live dashboard state, kept up to date over the backend WebSocket (/ws).
//
// The backend sends one "snapshot" on connect, then small updates:
//   reading (one device), summary (KPIs, ≤1/s), alert, notification.
// We also keep the last 60 readings per device in the browser for the charts.
import { useCallback, useEffect, useReducer } from 'react'
import { api } from '../api/client'

const HISTORY = 60 // readings per device = 60 simulated minutes

const initial = {
  connected: false,
  property: null,
  summary: null,
  rooms: {},   // room number -> view
  water: {},   // zone id     -> view
  cold: {},    // unit id     -> view
  alerts: {},  // alert id    -> alert
  notifications: [],
  history: {}, // device_id   -> [readings], oldest first
}

const keyed = (list, key) => Object.fromEntries(list.map((v) => [v[key], v]))

// Merge two reading lists by timestamp; on the same timestamp `b` wins.
function mergeHistory(a = [], b = []) {
  const byTs = new Map([...a, ...b].map((p) => [p.ts, p]))
  return [...byTs.values()].sort((x, y) => (x.ts < y.ts ? -1 : 1)).slice(-HISTORY)
}

const KIND = { room: ['rooms', 'room'], water: ['water', 'zone'], cold_chain: ['cold', 'unit'] }

function reducer(s, a) {
  switch (a.type) {
    case 'connected':
      return { ...s, connected: a.value }

    case 'snapshot': {
      const d = a.data
      return {
        ...s,
        property: d.property,
        summary: d.summary,
        rooms: keyed(d.rooms, 'room'),
        water: keyed(d.water, 'zone'),
        cold: keyed(d.cold_chain, 'unit'),
        alerts: keyed(d.alerts, 'id'),
        notifications: d.notifications,
      }
    }

    case 'reading': {
      const [map, key] = KIND[a.kind]
      const d = a.data
      return {
        ...s,
        [map]: { ...s[map], [d[key]]: d },
        history: { ...s.history, [d.device_id]: mergeHistory(s.history[d.device_id], [d]) },
      }
    }

    case 'summary': {
      // A silent device sends no readings, so the summary is what tells us it went offline
      const off = new Set(a.data.offline)
      const mark = (m) =>
        Object.fromEntries(Object.entries(m).map(([k, v]) => [k, off.has(v.device_id) ? { ...v, status: 'offline' } : v]))
      return { ...s, summary: a.data, rooms: mark(s.rooms), water: mark(s.water), cold: mark(s.cold) }
    }

    case 'alert':
      return { ...s, alerts: { ...s.alerts, [a.data.id]: a.data } }

    case 'notification': {
      const others = s.notifications.filter((n) => n.id !== a.data.id)
      return { ...s, notifications: [...others, a.data].slice(-100) }
    }

    case 'history': // seeded from the REST API; live readings already in the buffer win
      return { ...s, history: { ...s.history, [a.id]: mergeHistory(a.points, s.history[a.id]) } }

    default:
      return s
  }
}

// Fill the water and cold-chain charts right away instead of waiting 60 minutes
async function seedHistory(snapshot, dispatch) {
  try {
    const w = await api.waterHistory()
    for (const z of snapshot.water) dispatch({ type: 'history', id: z.device_id, points: w.zones[z.zone] || [] })
    await Promise.all(
      snapshot.cold_chain.map(async (u) =>
        dispatch({ type: 'history', id: u.device_id, points: await api.coldHistory(u.unit) }),
      ),
    )
  } catch {
    // charts still fill from live readings
  }
}

export function useLiveData() {
  const [state, dispatch] = useReducer(reducer, initial)

  useEffect(() => {
    let ws
    let retry
    let stopped = false

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => dispatch({ type: 'connected', value: true })
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        dispatch(msg) // server message types match the reducer actions
        if (msg.type === 'snapshot') seedHistory(msg.data, dispatch)
      }
      ws.onclose = () => {
        dispatch({ type: 'connected', value: false })
        if (!stopped) retry = setTimeout(connect, 2000) // backend restarted: keep trying
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(retry)
      ws.close()
    }
  }, [])

  const loadRoomHistory = useCallback(async (room) => {
    try {
      dispatch({ type: 'history', id: `thermo-${room}`, points: await api.roomHistory(room) })
    } catch {
      // fills from live readings
    }
  }, [])

  return { ...state, loadRoomHistory }
}

// Total flow of all zones per minute. The newest minute is dropped while its
// readings are still arriving (otherwise the line dips at the right edge).
export function totalFlow(history, zones) {
  const totals = new Map()
  for (const z of zones) {
    for (const p of history[z.device_id] || []) {
      const t = totals.get(p.ts) || { flow: 0, n: 0 }
      totals.set(p.ts, { flow: t.flow + p.flow_lpm, n: t.n + 1 })
    }
  }
  const rows = [...totals].sort(([a], [b]) => (a < b ? -1 : 1))
  if (rows.length > 1 && rows.at(-1)[1].n < rows.at(-2)[1].n) rows.pop()
  return rows.map(([ts, t]) => ({ ts, flow_lpm: Math.round(t.flow * 100) / 100 }))
}
