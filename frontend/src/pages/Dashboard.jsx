// The one-page operations console: header, fault simulator, KPIs, the three demos, and the AI rail.
import { useCallback, useEffect, useState } from 'react'
import { useLiveData } from '../hooks/useLiveData'
import AlertFeed from '../components/AlertFeed.jsx'
import ColdChainPanel from '../components/ColdChainPanel.jsx'
import FaultBar from '../components/FaultBar.jsx'
import FloorMap from '../components/FloorMap.jsx'
import KpiStrip from '../components/KpiStrip.jsx'
import NotificationLog from '../components/NotificationLog.jsx'
import RoomDetail from '../components/RoomDetail.jsx'
import Toasts from '../components/Toasts.jsx'
import WaterPanel from '../components/WaterPanel.jsx'

function Panel({ id, eyebrow, title, meta, children, className = '' }) {
  return (
    <section id={id} className={`panel ${className}`} aria-label={title}>
      <header className="panel__head">
        <div>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2 className="panel__title">{title}</h2>
        </div>
        {meta && <div className="panel__meta">{meta}</div>}
      </header>
      {children}
    </section>
  )
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const t = document.documentElement.dataset.theme
    return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  })
  function toggle() {
    const next = dark ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try { localStorage.setItem('theme', next) } catch { /* private mode: theme just isn't remembered */ }
    setDark(!dark)
  }
  return (
    <button type="button" className="iconbtn" onClick={toggle} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>
      {dark ? '☀' : '☾'}
    </button>
  )
}

// "2026-10-26T06:39:00+05:30" -> hotel-local time and date, without timezone conversion
function hotelClock(iso) {
  if (!iso) return ['--:--', '']
  const day = new Date(`${iso.slice(0, 10)}T12:00:00`)
  return [iso.slice(11, 16), day.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })]
}

export default function Dashboard() {
  const live = useLiveData()
  const { loadRoomHistory } = live
  const [room, setRoom] = useState('207')
  useEffect(() => { loadRoomHistory(room) }, [room, loadRoomHistory])

  // Jump from a notification / alert to the place on the dashboard where the fault is
  const [focus, setFocus] = useState(null)
  const open = useCallback((item) => {
    const device = item.device_id || item.source
    if (item.room) setRoom(item.room)
    const target = { 'Guest rooms': 'sec-rooms', 'Water & leaks': 'sec-water', 'Kitchen cold chain': 'sec-cold' }[item.section]
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setFocus(device)
    setTimeout(() => setFocus((f) => (f === device ? null : f)), 4000)
  }, [])

  const s = live.summary
  const [time, date] = hotelClock(s?.sim_time)
  const openAlerts = Object.values(live.alerts).filter((a) => a.status === 'open').length
  const leaks = Object.values(live.water).filter((z) => z.status === 'leak').length
  const coldIssues = Object.values(live.cold).filter((u) => ['breach', 'door_open', 'offline'].includes(u.status)).length
  const wasting = Object.values(live.rooms).filter((r) => r.status === 'wasting').length

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="8" />
            <path d="M6 17h5l3-7 4 13 3-6h5" />
          </svg>
          <div>
            <h1 className="brand__name">{live.property?.name || 'Hotel'}</h1>
            <div className="brand__sub">Operations console · Bengaluru</div>
          </div>
        </div>
        <div className="topbar__right">
          <span className={`live ${live.connected ? 'live--on' : 'live--off'}`} role="status">
            <span className="live__dot" aria-hidden="true" />
            {live.connected ? 'Live · AI monitoring' : 'Reconnecting…'}
          </span>
          <div className="clock" title="Simulated hotel time (IST)">
            <span className="clock__time num">{time}</span>
            <span className="clock__date">{date} · IST</span>
          </div>
          <div className="streams"><span className="num">{s?.streams ?? 0}</span> sensor streams</div>
          <ThemeToggle />
        </div>
      </header>

      <Toasts notifications={live.notifications} onOpen={open} />
      <FaultBar />
      <KpiStrip summary={s} />

      <div className="layout">
        <main className="main">
          <Panel id="sec-rooms" eyebrow="Demo 1 · continuous readings" title="Smart room energy" className="panel--rooms"
            meta={wasting ? <span className="meta-warn">▲ {wasting} room{wasting > 1 ? 's' : ''} wasting energy</span> : '20 rooms · 2 floors'}>
            <div className="demo1">
              <FloorMap rooms={live.rooms} selected={room} onSelect={setRoom} />
              <RoomDetail room={live.rooms[room]} history={live.history[`thermo-${room}`]}
                costPerKwh={live.property?.energy_cost_per_kwh} />
            </div>
          </Panel>

          <div className="demo23">
            <Panel id="sec-water" eyebrow="Demo 2 · event alarms" title="Water & leaks"
              meta={leaks ? <span className="meta-crit">! {leaks} leak{leaks > 1 ? 's' : ''}</span> : '5 zones'}>
              <WaterPanel water={live.water} history={live.history} focus={focus} />
            </Panel>
            <Panel id="sec-cold" eyebrow="Demo 3 · HACCP compliance" title="Kitchen cold chain"
              meta={coldIssues ? <span className="meta-crit">! {coldIssues} unit{coldIssues > 1 ? 's' : ''} need attention</span> : '5 units'}>
              <ColdChainPanel cold={live.cold} history={live.history} focus={focus} />
            </Panel>
          </div>
        </main>

        <aside className="rail">
          <Panel eyebrow="AI layer" title="Fault detection" meta={`${openAlerts} open`}>
            <AlertFeed alerts={live.alerts} streams={s?.streams} onOpen={open} />
          </Panel>
          <Panel eyebrow="To hotel management" title="Notifications" meta="On dashboard · WhatsApp/SMS on hold">
            <NotificationLog notifications={live.notifications} onOpen={open} />
          </Panel>
        </aside>
      </div>
    </div>
  )
}
