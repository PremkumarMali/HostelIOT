// Demo 1: the selected room's live readings + 60-minute temperature chart.
import LineChart from './LineChart.jsx'
import StatusPill from './StatusPill.jsx'
import { ROOM_STATUS } from './FloorMap.jsx'

const TONE = { guest_in: 'info', sold_out: 'info', unsold: 'neutral', wasting: 'warning', fault: 'critical', offline: 'neutral', no_data: 'neutral' }

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className="stat__value num">{value}</div>
      {sub && <div className="stat__sub">{sub}</div>}
    </div>
  )
}

export default function RoomDetail({ room, history, costPerKwh = 9 }) {
  if (!room) return null
  const has = room.temp_c != null
  return (
    <div className="roomdetail">
      <div className="roomdetail__head">
        <div>
          <div className="eyebrow">Selected room</div>
          <h3 className="roomdetail__title">Room <span className="num">{room.room}</span></h3>
        </div>
        <StatusPill tone={TONE[room.status]}>{ROOM_STATUS[room.status]}</StatusPill>
      </div>

      <div className="stats">
        <Stat label="Temperature" value={has ? `${room.temp_c.toFixed(1)} °C` : '—'} />
        <Stat label="Setpoint" value={has ? `${room.setpoint_c.toFixed(1)} °C` : '—'}
          sub={has && room.setpoint_c > 24 ? 'setback (vacant)' : has ? 'comfort' : null} />
        <Stat label="Humidity" value={has ? `${Math.round(room.humidity_rh)} %` : '—'} />
        <Stat label="Occupancy" value={!has ? '—' : room.occupied ? 'In room' : `Vacant ${room.vacant_min} min`}
          sub={has ? (room.pms_sold ? 'PMS: sold' : 'PMS: unsold') : null} />
        <Stat label="HVAC" value={!has ? '—' : room.hvac_on ? `On · ${room.hvac_kw} kW` : 'Off'} />
        <Stat label="HVAC energy" value={`${(room.kwh ?? 0).toFixed(2)} kWh`}
          sub={`₹${((room.kwh ?? 0) * costPerKwh).toFixed(0)} since start`} />
      </div>

      <div className="chart-head">
        <span className="chart-head__title">Room temperature · last 60 min</span>
        <span className="chart-key">
          <span className="chart-key__line" aria-hidden="true" />Temperature
          <span className="chart-key__line chart-key__line--ref" aria-hidden="true" />Setpoint
        </span>
      </div>
      <LineChart points={history} valueKey="temp_c" refKey="setpoint_c" unit="°C" label={`Room ${room.room} temperature`} height={170} />
    </div>
  )
}
