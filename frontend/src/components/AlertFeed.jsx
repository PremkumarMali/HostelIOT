// Right rail: AI fault detections, open first, newest first. Staff acknowledge from here.
import { useState } from 'react'
import { api } from '../api/client'

const METHOD = { rule: 'Rule', anomaly: 'Isolation Forest', forecast: 'Trend forecast', classifier: 'Random Forest' }
const hhmm = (ts) => ts.slice(11, 16)

function AlertCard({ a, onOpen }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  async function ack() {
    setBusy(true)
    setError(null)
    try {
      await api.ack(a.id) // the update itself arrives over the WebSocket
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  const pct = Math.round(a.confidence * 100)
  return (
    <li className={`alert alert--${a.severity}${a.status !== 'open' ? ' alert--done' : ''}`}>
      <div className="alert__top">
        <span className={`sev sev--${a.severity}`}>{a.severity === 'critical' ? '! Critical' : '▲ Warning'}</span>
        <span className="alert__time num">{hhmm(a.ts)}</span>
      </div>
      <button type="button" className="note__where note__where--link" onClick={() => onOpen(a)} title="Show on the dashboard">
        <span className="note__section">{a.section}</span>
        <span className="note__loc">{a.location}</span>
      </button>
      <div className="alert__title">{a.title}</div>
      <div className="alert__detail">{a.detail}</div>
      <div className="alert__conf">
        <span>Confidence</span>
        <span className="meter" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Confidence">
          <span className="meter__fill" style={{ width: `${pct}%` }} />
        </span>
        <span className="num">{pct}%</span>
      </div>
      <div className="alert__action"><strong>Action:</strong> {a.action}</div>
      <div className="alert__meta">
        {a.method.split('+').map((m) => <span key={m} className="chip">{METHOD[m] || m}</span>)}
        <span className="chip chip--mono">{a.source}</span>
        {a.escalated && <span className="chip chip--crit">▲ Escalated to GM</span>}
      </div>
      {a.status === 'open' ? (
        <button type="button" className="btn btn--primary btn--block" onClick={ack} disabled={busy}>
          {busy ? 'Acknowledging…' : 'Acknowledge'}
        </button>
      ) : (
        <div className="alert__acked">✓ {a.status === 'resolved' ? 'Resolved' : `Acknowledged by ${a.acked_by}`}</div>
      )}
      {error && <div className="form-error" role="alert">{error}</div>}
    </li>
  )
}

export default function AlertFeed({ alerts, streams, onOpen }) {
  // open first, then acknowledged, newest first; only the 5 most recent resolved ones stay visible
  const rank = { open: 0, acknowledged: 1, resolved: 2 }
  const all = Object.values(alerts).sort((x, y) => rank[x.status] - rank[y.status] || y.ts.localeCompare(x.ts))
  const active = all.filter((a) => a.status !== 'resolved')
  const resolved = all.filter((a) => a.status === 'resolved')
  const list = [...active, ...resolved.slice(0, 5)]
  if (!list.length) {
    return (
      <div className="empty">
        <div className="empty__icon" aria-hidden="true">✓</div>
        <div className="empty__title">No faults detected</div>
        <div className="empty__text">AI is watching {streams ?? 0} sensor streams. Use the fault simulator above to trigger one.</div>
      </div>
    )
  }
  return (
    <>
      {!active.length && <div className="alerts__clear">✓ No open faults · last resolved below</div>}
      <ul className="alerts" aria-live="polite">{list.map((a) => <AlertCard key={a.id} a={a} onOpen={onOpen} />)}</ul>
      {resolved.length > 5 && <div className="footnote">{resolved.length - 5} older resolved alerts not shown</div>}
    </>
  )
}
