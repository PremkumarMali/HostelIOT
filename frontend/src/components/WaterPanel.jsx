// Demo 2: total water flow (last 60 min) + every zone with its probe status.
import { useMemo } from 'react'
import { totalFlow } from '../hooks/useLiveData'
import LineChart from './LineChart.jsx'
import StatusPill, { WATER_STATUS } from './StatusPill.jsx'

export default function WaterPanel({ water, history, focus }) {
  const zones = Object.values(water)
  const total = useMemo(() => totalFlow(history, Object.values(water)), [history, water])
  const now = total.at(-1)?.flow_lpm

  return (
    <>
      <div className="chart-head">
        <span className="chart-head__title">Total flow · last 60 min</span>
        <span className="chart-head__value num">{now != null ? `${now.toFixed(1)} L/min` : '—'}</span>
      </div>
      <LineChart points={total} valueKey="flow_lpm" unit="L/min" label="Total water flow" area height={150} />

      <table className="table">
        <thead>
          <tr><th scope="col">Zone</th><th scope="col" className="r">Flow</th><th scope="col" className="r">Normal</th><th scope="col">Probe</th></tr>
        </thead>
        <tbody>
          {zones.map((z) => {
            const [tone, text] = WATER_STATUS[z.status]
            return (
              <tr key={z.zone} className={`${z.status === 'leak' ? 'row--critical' : ''}${focus === z.device_id ? ' is-focus' : ''}`}>
                <td>{z.name}</td>
                <td className="r num">{z.flow_lpm != null ? z.flow_lpm.toFixed(1) : '—'}</td>
                <td className="r num muted">{z.normal_flow_lpm.toFixed(1)}</td>
                <td><StatusPill tone={tone}>{text}</StatusPill></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="footnote">Flow in L/min. “High flow” = more than 2× the zone’s normal flow.</p>
    </>
  )
}
