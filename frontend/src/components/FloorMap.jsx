// Demo 1: both guest floors as a grid of rooms, coloured by status. Click a room for details.
export const ROOM_STATUS = {
  guest_in: 'Guest in room',
  sold_out: 'Sold, guest out',
  unsold: 'Unsold',
  wasting: 'AC wasting energy',
  fault: 'Fault',
  offline: 'Offline',
  no_data: 'No data',
}
const SHORT = { wasting: 'AC waste', fault: 'Fault', offline: 'Offline' } // printed on the tile itself

export default function FloorMap({ rooms, selected, onSelect }) {
  const list = Object.values(rooms)
  const floors = [...new Set(list.map((r) => r.area))].sort().reverse() // top floor first
  const used = new Set(list.map((r) => r.status))

  return (
    <div className="floormap">
      {floors.map((floor) => (
        <div key={floor} className="floormap__floor">
          <div className="floormap__label">Floor {floor.replace('floor', '')}</div>
          <div className="floormap__grid" role="group" aria-label={`Floor ${floor.replace('floor', '')}`}>
            {list.filter((r) => r.area === floor).map((r) => (
              <button key={r.room} type="button"
                className={`room room--${r.status}${selected === r.room ? ' room--selected' : ''}`}
                aria-pressed={selected === r.room}
                aria-label={`Room ${r.room}: ${ROOM_STATUS[r.status]}${r.temp_c != null ? `, ${r.temp_c} °C` : ''}`}
                onClick={() => onSelect(r.room)}>
                <span className="room__no num">{r.room}</span>
                <span className="room__temp num">{r.temp_c != null ? `${r.temp_c.toFixed(1)}°` : '—'}</span>
                {SHORT[r.status] && <span className="room__flag">{SHORT[r.status]}</span>}
              </button>
            ))}
          </div>
        </div>
      ))}
      <ul className="legend" aria-label="Room status legend">
        {Object.entries(ROOM_STATUS).filter(([k]) => k !== 'no_data' || used.has(k)).map(([k, text]) => (
          <li key={k}><span className={`legend__swatch room--${k}`} aria-hidden="true" />{text}</li>
        ))}
      </ul>
    </div>
  )
}
