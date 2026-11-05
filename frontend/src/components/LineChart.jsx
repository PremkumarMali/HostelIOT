// Hand-built SVG line chart (no chart library), used by all three demos.
//   points    readings with an ISO `ts` (oldest first)
//   valueKey  field to plot, e.g. "temp_c"
//   refKey    optional reference series drawn as a thin step line (e.g. setpoint)
//   band      optional {min, max} safe band, shaded
//   area      fill under the line from 0 (for flows)
//   compact   sparkline: no axes
// Hovering shows a crosshair + tooltip with the exact time and value.
import { useLayoutEffect, useRef, useState } from 'react'

function useWidth(ref) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [ref])
  return width
}

// About `count` round tick values between lo and hi (1, 2, 2.5, 5 × 10^n steps)
function niceTicks(lo, hi, count = 4) {
  const raw = (hi - lo) / count || 1
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const ticks = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(Number(v.toFixed(6)))
  return ticks
}

const hhmm = (ts) => ts.slice(11, 16) // ISO with +05:30 offset -> hotel local "HH:MM"

export default function LineChart({
  points = [], valueKey, refKey, refLabel = 'Setpoint', band, unit = '', label = '',
  height = 160, area = false, compact = false, digits = 1,
}) {
  const wrapRef = useRef(null)
  const width = useWidth(wrapRef)
  const [hover, setHover] = useState(null)

  const data = points.filter((p) => Number.isFinite(p[valueKey]))
  const m = compact ? { t: 4, r: 6, b: 4, l: 4 } : { t: 12, r: 14, b: 24, l: 42 }

  // The wrapper div is always the same element, so the ResizeObserver keeps measuring it
  const wrap = (content, empty = false) => (
    <div ref={wrapRef} className={`chart${compact ? ' chart--compact' : ''}${empty ? ' chart--empty' : ''}`} style={{ height }}>
      {content}
    </div>
  )
  if (width === 0 || data.length < 2) return wrap(<span>{compact ? '' : 'Collecting readings…'}</span>, true)

  // ---- scales ----
  const xs = data.map((p) => Date.parse(p.ts))
  const vals = data.map((p) => p[valueKey])
  const refs = refKey ? data.map((p) => p[refKey]) : []
  const all = [...vals, ...refs.filter(Number.isFinite), ...(band ? [band.min, band.max] : [])]
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  const pad = (hi - lo) * 0.12 || 1
  lo = area ? Math.min(0, lo) : lo - pad
  hi += pad
  const x0 = xs[0]
  const x1 = xs.at(-1)
  const x = (t) => m.l + ((t - x0) / (x1 - x0 || 1)) * (width - m.l - m.r)
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (height - m.t - m.b)

  // ---- paths ----
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${x(xs[i]).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const fill = area ? `${line}L${x(x1)},${y(lo)}L${x(x0)},${y(lo)}Z` : null
  const ref = refKey
    ? refs.map((r, i) => (i ? `H${x(xs[i]).toFixed(1)}V${y(r).toFixed(1)}` : `M${x(x0)},${y(r).toFixed(1)}`)).join('')
    : null
  const yTicks = compact ? [] : niceTicks(lo, hi)
  const xTickIdx = compact ? [] : [0, Math.round((data.length - 1) / 3), Math.round((2 * (data.length - 1)) / 3), data.length - 1]

  // ---- hover: nearest reading to the pointer ----
  function onMove(e) {
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left
    let best = 0
    xs.forEach((t, i) => { if (Math.abs(x(t) - px) < Math.abs(x(xs[best]) - px)) best = i })
    setHover(best)
  }

  const last = data.length - 1
  const fmt = (v) => `${v.toFixed(digits)}${unit ? ` ${unit}` : ''}`
  const summary = `${label}: now ${fmt(vals[last])}, last ${data.length} min range ${fmt(Math.min(...vals))} to ${fmt(Math.max(...vals))}`
  const h = hover ?? null
  const tipLeft = h === null ? 0 : Math.min(Math.max(x(xs[h]), 70), width - 70)

  return wrap(
    <>
      <svg width={width} height={height} role="img" aria-label={summary}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {band && (
          <g className="chart__band">
            <rect x={m.l} width={width - m.l - m.r} y={y(band.max)} height={Math.max(0, y(band.min) - y(band.max))} />
            <line x1={m.l} x2={width - m.r} y1={y(band.max)} y2={y(band.max)} />
            <line x1={m.l} x2={width - m.r} y1={y(band.min)} y2={y(band.min)} />
          </g>
        )}
        {yTicks.map((t) => (
          <g key={t} className="chart__tick">
            <line x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} />
            <text x={m.l - 8} y={y(t)} dy="0.32em" textAnchor="end">{t}</text>
          </g>
        ))}
        {!compact && <line className="chart__axis" x1={m.l} x2={width - m.r} y1={height - m.b} y2={height - m.b} />}
        {xTickIdx.map((i, k) => (
          <text key={k} className="chart__xlabel" x={x(xs[i])} y={height - 6}
            textAnchor={k === 0 ? 'start' : k === xTickIdx.length - 1 ? 'end' : 'middle'}>
            {hhmm(data[i].ts)}
          </text>
        ))}
        {!compact && unit && <text className="chart__unit" x={m.l - 8} y={m.t - 2} textAnchor="end">{unit}</text>}
        {fill && <path className="chart__area" d={fill} />}
        {ref && <path className="chart__ref" d={ref} />}
        <path className="chart__line" d={line} />
        <circle className="chart__dot" cx={x(xs[last])} cy={y(vals[last])} r={compact ? 3 : 4} />
        {h !== null && (
          <g>
            <line className="chart__crosshair" x1={x(xs[h])} x2={x(xs[h])} y1={m.t} y2={height - m.b} />
            <circle className="chart__dot" cx={x(xs[h])} cy={y(vals[h])} r={4} />
          </g>
        )}
      </svg>
      {h !== null && (
        <div className="chart__tip" style={{ left: tipLeft }}>
          <span className="chart__tip-time">{hhmm(data[h].ts)}</span>
          <span className="num">{fmt(vals[h])}</span>
          {refKey && Number.isFinite(refs[h]) && <span className="chart__tip-ref">{refLabel} {fmt(refs[h])}</span>}
        </div>
      )}
    </>,
  )
}
