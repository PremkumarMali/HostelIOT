// Right rail: notifications to hotel management, shown on the dashboard
// (WhatsApp / SMS are on hold). Each one says WHICH SECTION and WHICH ROOM / UNIT;
// clicking it jumps to that place on the dashboard.
export const NOTE = {
  critical: { icon: '!', label: 'Critical' },
  warning: { icon: '▲', label: 'Warning' },
  info: { icon: 'i', label: 'Update' },
  resolved: { icon: '✓', label: 'Resolved' },
}
const hhmm = (ts) => ts.slice(11, 16)

export function NoteBody({ n }) {
  const lines = n.text.split('\n').slice(2) // line 0 = title, line 1 = "Where: ..." (shown as chips)
  return (
    <>
      <div className="note__where">
        <span className="note__section">{n.section}</span>
        <span className="note__loc">{n.location}</span>
      </div>
      <div className="note__title">{n.title}</div>
      {lines.map((l, i) => <div key={i} className="note__text">{l}</div>)}
    </>
  )
}

export default function NotificationLog({ notifications, onOpen }) {
  if (!notifications.length) {
    return (
      <div className="empty empty--small">
        <div className="empty__text">
          No notifications yet. When the AI finds a fault, managers see here which section and which room or unit it is in.
        </div>
      </div>
    )
  }
  return (
    <ul className="notes">
      {[...notifications].reverse().map((n) => {
        const s = NOTE[n.severity]
        return (
          <li key={n.id}>
            <button type="button" className={`note note--${n.severity}`} onClick={() => onOpen(n)}
              title="Show on the dashboard">
              <span className="note__icon" aria-hidden="true">{s.icon}</span>
              <span className="note__main">
                <span className="note__top">
                  <span className="note__sev">{s.label}</span>
                  <span className="note__time num">{hhmm(n.ts)}</span>
                </span>
                <NoteBody n={n} />
                <span className="note__for">For: {n.recipients.join(', ') || 'Duty team'}</span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
