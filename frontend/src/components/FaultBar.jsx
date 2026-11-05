// Demo-mode fault simulator: buttons that break things on purpose so the AI has something to find.
// Hidden completely when the backend has DEMO_MODE=false (the API returns 404).
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'

const FAULTS = [
  { type: 'leak', label: 'Water leak', where: 'Laundry' },
  { type: 'compressor_failure', label: 'Chiller failure', where: 'Walk-in chiller' },
  { type: 'hvac_stuck_on', label: 'AC on in empty room', where: 'Room 207' },
  { type: 'sensor_offline', label: 'Sensor offline', where: 'Bar fridge' },
  { type: 'door_left_open', label: 'Door left open', where: 'Pastry fridge' },
]

export default function FaultBar() {
  const [sim, setSim] = useState(null) // simulator status
  const [hidden, setHidden] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setSim(await api.simStatus())
      setError(null)
    } catch (e) {
      if (e.status === 404) setHidden(true)
      else setError(e.status === 503 ? 'Simulator is not running' : e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000) // faults can also be set from the CLI
    return () => clearInterval(id)
  }, [refresh])

  async function run(action) {
    setBusy(true)
    try {
      setSim(await action())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (hidden) return null
  const active = new Map((sim?.faults || []).map((f) => [f.fault, f.device_id]))

  return (
    <section className="faultbar" aria-label="Fault simulator">
      <div className="faultbar__label">
        <span className="faultbar__tag">Demo</span>
        Fault simulator
      </div>
      <div className="faultbar__buttons">
        {FAULTS.map((f) => {
          const on = active.has(f.type)
          return (
            <button key={f.type} type="button" className={`btn btn--fault${on ? ' is-on' : ''}`}
              aria-pressed={on} disabled={busy || !sim}
              title={on ? `Click to clear (${active.get(f.type)})` : `Inject at ${f.where}`}
              onClick={() => run(() => (on ? api.clearFaults(active.get(f.type)) : api.injectFault(f.type)))}>
              <span className="btn__dot" aria-hidden="true" />
              {f.label}
              <span className="btn__where">{f.where}</span>
            </button>
          )
        })}
      </div>
      <div className="faultbar__controls">
        <button type="button" className="btn" disabled={busy || !sim} onClick={() => run(api.togglePause)}>
          {sim?.paused ? '▶ Resume' : '❚❚ Pause'}
        </button>
        <button type="button" className="btn" disabled={busy || !sim || !active.size} onClick={() => run(() => api.clearFaults())}>
          Clear all
        </button>
      </div>
      {error && <div className="faultbar__error" role="status">{error}</div>}
    </section>
  )
}
