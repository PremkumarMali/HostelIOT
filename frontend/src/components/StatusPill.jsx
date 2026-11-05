// Status pill: colour + icon + text, so state never depends on colour alone.
// tone: good | warning | critical | info | neutral
const ICON = { good: '✓', warning: '▲', critical: '!', info: '●', neutral: '–' }

export default function StatusPill({ tone = 'neutral', children }) {
  return (
    <span className={`pill pill--${tone}`}>
      <span className="pill__icon" aria-hidden="true">{ICON[tone]}</span>
      {children}
    </span>
  )
}

// Device status (from the backend) -> pill tone + label, per demo
export const COLD_STATUS = {
  ok: ['good', 'OK'],
  at_risk: ['warning', 'At risk'],
  door_open: ['warning', 'Door open'],
  breach: ['critical', 'Breach'],
  offline: ['neutral', 'Offline'],
  no_data: ['neutral', 'No data'],
}

export const WATER_STATUS = {
  ok: ['good', 'Dry'],
  high: ['warning', 'High flow'],
  leak: ['critical', 'Leak'],
  offline: ['neutral', 'Offline'],
  no_data: ['neutral', 'No data'],
}
