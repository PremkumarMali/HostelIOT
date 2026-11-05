// Right rail: AI fault detections, open first, newest first. Staff acknowledge from here.
import { useState } from 'react'
import { api } from '../api/client'

const METHOD = { rule: 'Rule', anomaly: 'Anomaly model', forecast: 'Forecast', classifier: 'Fault classifier' }
const hhmm = (ts) => ts.slice(11, 16)

function AlertCard({ a }) {
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
        <span className="chip">{METHOD[a.method] || a.method}</span>
        <span className="chip chip--mono">{a.source}</span>
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

export default function AlertFeed({ alerts, streams }) {
  // open alerts first, then newest first
  const list = Object.values(alerts).sort(
    (x, y) => (y.status === 'open') - (x.status === 'open') || y.ts.localeCompare(x.ts),
  )
  if (!list.length) {
    return (
      <div className="empty">
        <div className="empty__icon" aria-hidden="true">✓</div>
        <div className="empty__title">No faults detected</div>
        <div className="empty__text">AI is watching {streams ?? 0} sensor streams. Use the fault simulator above to trigger one.</div>
      </div>
    )
  }
  return <ul className="alerts" aria-live="polite">{list.map((a) => <AlertCard key={a.id} a={a} />)}</ul>
}
