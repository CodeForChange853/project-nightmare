import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import CountUp from './CountUp'
import Icon from './Icon'

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const COLS = 30
const ROWS = 7

const secs = (v) => `${(v / 1000).toFixed(1)}s`

function ResponseTime({ avgMs, history }) {
  const grid = useRef(null)
  const last = history.at(-1)
  const max = Math.max(1, ...history.map((h) => h.ms))
  const cols = Array.from({ length: COLS }, (_, i) => history[history.length - COLS + i] ?? null)
  const speed = !avgMs ? null : avgMs < 6000 ? 'Quick' : avgMs < 15000 ? 'Steady' : 'Slow'

  // the newest column rises in when a reply lands
  useLayoutEffect(() => {
    if (!history.length || reducedMotion()) return
    const dots = grid.current?.querySelectorAll('[data-col="latest"] [data-on]')
    if (!dots?.length) return
    const t = gsap.from(dots, { scale: 0, opacity: 0, duration: 0.35, stagger: { each: 0.04, from: 'end' }, ease: 'back.out(3)' })
    return () => t.kill()
  }, [history.length])

  return (
    <section className="overflow-hidden rounded-2xl border border-scar/50 bg-[linear-gradient(135deg,rgba(120,10,30,0.45),rgba(19,7,10,0.85)_60%)] p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[14px] text-bone">Model response time</h3>
        {speed && (
          <span
            className={`rounded-md border px-2 py-0.5 text-[11px] ${
              speed === 'Slow' ? 'border-bile/50 bg-bile/10 text-bile' : 'border-ember/40 bg-ember/10 text-ember'
            }`}
          >
            {speed}
          </span>
        )}
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div>
          <p className="font-display text-[52px] font-bold leading-[0.85] text-bone">
            {avgMs ? <CountUp value={avgMs} format={secs} /> : '–'}
          </p>
          <p className="mt-1.5 text-[11px] text-smoke">Average for all agy calls</p>
          {last && avgMs > 0 && (
            <p className={`mt-1 text-[12px] ${last.ms <= avgMs ? 'text-ember' : 'text-bile'}`}>
              Last reply {secs(last.ms)}, {secs(Math.abs(avgMs - last.ms))} {last.ms <= avgMs ? 'faster' : 'slower'}
            </p>
          )}
        </div>
        <div
          ref={grid}
          className="flex shrink-0 items-end gap-[3px]"
          role="img"
          aria-label={
            history.length
              ? `Reply times this session, ${history.length} replies, latest ${secs(last.ms)}`
              : 'No replies yet this session'
          }
        >
          {cols.map((c, i) => {
            const on = c ? Math.max(1, Math.round((c.ms / max) * ROWS)) : 0
            const latest = c && c === last
            return (
              <div key={i} data-col={latest ? 'latest' : undefined} className="flex flex-col-reverse gap-[3px]">
                {Array.from({ length: ROWS }, (_, r) => (
                  <span
                    key={r}
                    data-on={r < on ? '' : undefined}
                    className={`h-[3px] w-[3px] rounded-full ${
                      r < on ? (latest ? 'bg-ember shadow-[0_0_6px_#ff5466]' : 'bg-ash/80') : 'bg-vein/80'
                    }`}
                  />
                ))}
              </div>
            )
          })}
        </div>
      </div>
      {!history.length && <p className="mt-3 text-[11px] text-smoke">Your first reply this session starts the chart.</p>}
    </section>
  )
}

function Stat({ icon, value, label, tone = 'text-bone' }) {
  return (
    <div className="tile rounded-2xl p-3.5">
      <div className="flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-full border border-scar/60 text-ember">
          <Icon name={icon} size={15} />
        </span>
        <CountUp value={value} className={`font-display text-[30px] font-bold leading-none ${tone}`} />
      </div>
      <p className="mt-2 text-[12px] text-ash">{label}</p>
    </div>
  )
}

/** One project / reminder / app as a card with its facts and action buttons (also the phone's project page). */
export function Selected({ item, readonly, disabled, onRun }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    if (reducedMotion()) return
    const t = gsap.from(ref.current.children, { y: 10, opacity: 0, duration: 0.4, stagger: 0.05, ease: 'power2.out' })
    return () => t.kill()
  }, [item.id])

  const actions = item.actions.filter((a) => !(readonly && a.full))
  const blocked = readonly && item.actions.some((a) => a.full)

  return (
    <section ref={ref} className="rounded-2xl border border-scar/40 bg-abyss/40 p-4">
      <div className="flex items-center gap-2 text-[12px] text-ash">
        <Icon name={item.icon} size={15} className="text-ember" />
        {item.kindLabel}
        {item.badge && (
          <span
            className={`ml-auto rounded-md border px-2 py-0.5 text-[11px] ${
              item.badge.tone === 'warn' ? 'border-bile/50 text-bile' : 'border-ember/40 bg-ember/10 text-ember'
            }`}
          >
            {item.badge.text}
          </span>
        )}
      </div>
      <h2 className="mt-2 break-words text-[24px] font-semibold leading-tight text-bone">{item.heading ?? item.title}</h2>
      {item.facts?.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
          {item.facts.map((f) => (
            <div key={f.label} className="min-w-0">
              <dt className="text-smoke">{f.label}</dt>
              <dd className="truncate text-bone" title={f.value}>
                {f.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {item.body && <p className="mt-3 text-[13px] leading-relaxed text-ash">{item.body}</p>}
      {blocked && <p className="mt-3 text-[12px] text-bile">Opening and running things is turned off in read-only sessions.</p>}
      {actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {actions.map((a, i) => (
            <button
              key={a.label}
              type="button"
              disabled={disabled}
              onClick={() => onRun(a.command)}
              className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] disabled:opacity-40 ${
                i === 0
                  ? 'bg-gradient-to-b from-crimson to-[#9e0d2b] font-semibold text-white shadow-[0_8px_24px_-10px_rgba(220,20,60,0.9)] hover:brightness-110'
                  : 'border border-scar/70 text-ash hover:border-ember/60 hover:text-bone'
              }`}
            >
              {a.label}
              {i === 0 && <Icon name="chevron" size={14} />}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

export default function Dossier({ item, status, offline, history, readonly, disabled, onRun, onRetry }) {
  const calls = status?.llm_calls
  return (
    <div className="flex flex-col gap-3">
      {offline ? (
        <section className="rounded-2xl border border-scar/40 bg-abyss/40 p-4">
          <h2 className="text-[20px] font-semibold text-bone">Nightmare can’t reach its backend</h2>
          <p className="mt-2 text-[13px] leading-relaxed text-ash">
            Start it with <code className="font-mono text-[12px] text-bone">python -m backend</code> or{' '}
            <code className="font-mono text-[12px] text-bone">scripts\start_nightmare.ps1</code>. This page checks again every
            10 seconds.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 flex items-center gap-1.5 rounded-xl border border-scar/70 px-3.5 py-2 text-[13px] text-ash hover:text-bone"
          >
            <Icon name="refresh" size={14} /> Check now
          </button>
        </section>
      ) : item ? (
        <Selected item={item} readonly={readonly} disabled={disabled} onRun={onRun} />
      ) : (
        <section className="rounded-2xl border border-dashed border-scar/50 p-4">
          <h2 className="text-[16px] font-medium text-bone">Pick a node to inspect it</h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ash">
            Choose a group next to the eye, then an item from the arc. Double-click an item to run its main action.
          </p>
        </section>
      )}

      {calls ? (
        <ResponseTime avgMs={calls.avg_ms} history={history} />
      ) : (
        <div className="shimmer h-[150px] rounded-2xl" />
      )}

      {calls ? (
        <div className="grid grid-cols-2 gap-3">
          <Stat icon="check" value={calls.today_ok} label="Replies today" />
          <Stat icon="warn" value={calls.today_failed} label="Failed today" tone={calls.today_failed ? 'text-bile' : 'text-bone'} />
          <Stat icon="spark" value={calls.total} label="All-time agy calls" />
          <Stat icon="bell" value={status.notes?.length ?? 0} label="Open reminders" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="shimmer h-[92px] rounded-2xl" />
          ))}
        </div>
      )}
    </div>
  )
}
