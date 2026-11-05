// Right rail: every WhatsApp / SMS sent to management, with delivery ticks.
const STATUS = {
  queued: ['○', 'Queued'],
  sent: ['✓', 'Sent'],
  delivered: ['✓✓', 'Delivered'],
  failed: ['✕', 'Failed'],
}
const hhmm = (ts) => ts.slice(11, 16)

export default function NotificationLog({ notifications }) {
  if (!notifications.length) {
    return (
      <div className="empty empty--small">
        <div className="empty__text">No messages yet. Managers are messaged automatically when the AI raises an alert.</div>
      </div>
    )
  }
  return (
    <ul className="msgs">
      {[...notifications].reverse().map((n) => {
        const [tick, text] = STATUS[n.status]
        return (
          <li key={n.id} className="msg">
            <span className={`badge badge--${n.channel}`}>{n.channel === 'whatsapp' ? 'WA' : 'SMS'}</span>
            <div className="msg__body">
              <div className="msg__top">
                <span className="msg__to">{n.recipient}</span>
                <span className="msg__num num">{n.to_masked}</span>
                <span className="msg__time num">{hhmm(n.ts)}</span>
              </div>
              <div className="msg__text" title={n.text}>{n.text}</div>
            </div>
            <span className={`ticks ticks--${n.status}`} title={text}>
              <span aria-hidden="true">{tick}</span><span className="sr-only">{text}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
