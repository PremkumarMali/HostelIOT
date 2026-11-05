// Pop-up toasts (top-right) for every NEW notification, so nobody misses a fault.
// Notifications already present when the page loads are not popped up again.
// Critical toasts stay until closed; others disappear after 10 s. One toast per alert.
import { useEffect, useRef, useState } from 'react'
import { NOTE, NoteBody } from './NotificationLog.jsx'

export default function Toasts({ notifications, onOpen }) {
  const [toasts, setToasts] = useState([])
  const seen = useRef(null)

  useEffect(() => {
    if (seen.current === null) {             // first render: remember what was already there
      seen.current = new Set(notifications.map((n) => n.id))
      return
    }
    const fresh = notifications.filter((n) => !seen.current.has(n.id))
    if (!fresh.length) return
    fresh.forEach((n) => seen.current.add(n.id))
    // newest first; a newer notification about the same alert replaces the older toast
    const newest = [...fresh].reverse().filter((n, i, all) => all.findIndex((x) => x.alert_id === n.alert_id) === i)
    const ids = new Set(newest.map((n) => n.alert_id))
    setToasts((t) => [...newest, ...t.filter((x) => !ids.has(x.alert_id))].slice(0, 3))
    fresh.filter((n) => n.severity !== 'critical').forEach((n) =>
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== n.id)), 10000))
  }, [notifications])

  const close = (id) => setToasts((t) => t.filter((x) => x.id !== id))

  return (
    <div className="toasts" aria-live="assertive">
      {toasts.map((n) => (
        <div key={n.id} className={`toast note--${n.severity}`} role="alert">
          <span className="note__icon" aria-hidden="true">{NOTE[n.severity].icon}</span>
          <button type="button" className="toast__body" onClick={() => { onOpen(n); close(n.id) }}>
            <NoteBody n={n} />
            <span className="toast__hint">Click to show on the dashboard</span>
          </button>
          <button type="button" className="toast__close" aria-label="Close notification" onClick={() => close(n.id)}>×</button>
        </div>
      ))}
    </div>
  )
}
