// Six headline numbers across the top of the console.
const inr = (n) => `₹${Math.round(n).toLocaleString('en-IN')}`
const num = (n, d = 0) => (n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: d })

function Tile({ label, value, unit, sub, tone }) {
  return (
    <div className={`kpi${tone ? ` kpi--${tone}` : ''}`}>
      <div className="kpi__label">{label}</div>
      <div className="kpi__value num">
        {value}
        {unit && <span className="kpi__unit">{unit}</span>}
      </div>
      <div className="kpi__sub">{sub}</div>
    </div>
  )
}

export default function KpiStrip({ summary: s }) {
  if (!s) return <div className="kpis kpis--loading" aria-busy="true" />
  const compliance = s.cold_compliance_pct
  return (
    <section className="kpis" aria-label="Key figures">
      <Tile label="Rooms sold" value={`${s.rooms_sold}/${s.rooms_total}`}
        sub={`${s.guests_in} guest${s.guests_in === 1 ? '' : 's'} in room now`} />
      <Tile label="Energy saved" value={num(s.energy_saved_kwh, 1)} unit="kWh"
        sub={`${inr(s.energy_saved_inr)} · HVAC used ${num(s.hvac_kwh, 1)} kWh`} />
      <Tile label="Water used" value={num(s.water_used_l)} unit="L" sub="all 5 zones, since start" />
      <Tile label="Cold-chain compliance" value={compliance == null ? '—' : num(compliance, 1)} unit={compliance == null ? '' : '%'}
        sub="readings inside safe band" tone={compliance != null && compliance < 95 ? 'warning' : null} />
      <Tile label="Open alerts" value={s.open_alerts}
        sub={s.critical_alerts ? `${s.critical_alerts} critical` : 'none critical'}
        tone={s.critical_alerts ? 'critical' : s.open_alerts ? 'warning' : null} />
      <Tile label="Notifications" value={s.messages_sent} sub="to managers, on this dashboard" />
    </section>
  )
}
