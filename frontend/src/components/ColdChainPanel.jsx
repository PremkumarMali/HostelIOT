// Demo 3: every fridge / freezer with its safe band, a shaded-band sparkline and HACCP status.
import LineChart from './LineChart.jsx'
import StatusPill, { COLD_STATUS } from './StatusPill.jsx'

export default function ColdChainPanel({ cold, history, focus }) {
  return (
    <ul className="units">
      {Object.values(cold).map((u) => {
        const [tone, text] = COLD_STATUS[u.status]
        return (
          <li key={u.unit} className={`unit${tone === 'critical' ? ' unit--critical' : ''}${focus === u.device_id ? ' is-focus' : ''}`}>
            <div className="unit__info">
              <div className="unit__name">{u.name}</div>
              <div className="unit__band">Safe <span className="num">{u.safe_min_c} to {u.safe_max_c} °C</span></div>
            </div>
            <div className="unit__temp num">{u.temp_c != null ? `${u.temp_c.toFixed(1)}°` : '—'}</div>
            <div className="unit__spark">
              <LineChart points={history[u.device_id]} valueKey="temp_c" unit="°C" compact height={40}
                band={{ min: u.safe_min_c, max: u.safe_max_c }} label={`${u.name} temperature`} />
            </div>
            <div className="unit__status">
              <StatusPill tone={tone}>{text}</StatusPill>
              {u.breach_in_min != null && u.status === 'at_risk' && (
                <div className="unit__eta">breach in ~<span className="num">{Math.round(u.breach_in_min)}</span> min</div>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
