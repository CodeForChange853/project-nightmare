import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { closeDb, deleteDbFact, deleteDbNote, getDbActions, getDbRecords, openDb } from '../api'
import Icon from './Icon'

const TABS = [
  { key: 'notes', label: 'Reminders' },
  { key: 'facts', label: 'Memory' },
  { key: 'actions', label: 'Activity log' },
  { key: 'llm_calls', label: 'Model calls' },
]

const GROUPS = [
  { key: '', label: 'All' },
  { key: 'access', label: 'Logins & access' },
  { key: 'actions', label: 'Actions' },
  { key: 'reminders', label: 'Reminders' },
  { key: 'questions', label: 'Questions' },
]
const PROBLEM_RE = /fail|error|block|limit|cancel/

const stamp = (ts) => {
  const d = new Date(ts)
  return Number.isNaN(d.getTime())
    ? ts
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

function Th({ children, className = '' }) {
  return <th className={`sticky top-0 bg-clot px-3 py-2 text-left text-[11px] font-medium text-smoke ${className}`}>{children}</th>
}

/**
 * "database access open" -> type the PIN (never spoken) -> read the SQLite records.
 * The token lives only in this component; closing, Esc, "database close" or the timer revokes it.
 */
export default function DatabasePanel({ onClose }) {
  const root = useRef(null)
  const card = useRef(null)
  const tokenRef = useRef(null)
  const [token, setToken] = useState(null)
  const [left, setLeft] = useState(0)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [records, setRecords] = useState(null)
  const [tab, setTab] = useState('notes')
  const [armed, setArmed] = useState(null) // note id waiting for a second click to delete
  const [filters, setFilters] = useState({ group: '', outcome: '', q: '' })
  const [activity, setActivity] = useState(null) // {items, more} for the Activity log tab
  const [loadingMore, setLoadingMore] = useState(false)

  const close = useCallback(() => {
    const t = tokenRef.current
    tokenRef.current = null
    if (t) closeDb(t).catch(() => {})
    onClose()
  }, [onClose])

  // revoke the token if the panel goes away any other way (e.g. the "database close" command)
  useEffect(
    () => () => {
      if (tokenRef.current) closeDb(tokenRef.current).catch(() => {})
    },
    [],
  )

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tl = gsap
      .timeline()
      .from(root.current, { opacity: 0, duration: 0.25 })
      .from(card.current, { y: 28, scale: 0.97, opacity: 0, duration: 0.5, ease: 'expo.out' }, 0.05)
    return () => tl.kill()
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  // countdown to the server-side expiry
  useEffect(() => {
    if (!token) return
    const id = setInterval(() => setLeft((s) => s - 1), 1000)
    return () => clearInterval(id)
  }, [token])
  useEffect(() => {
    if (token && left <= 0) close()
  }, [token, left, close])

  const load = useCallback(async (t) => {
    setBusy(true)
    setError('')
    try {
      setRecords(await getDbRecords(t))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [])

  const unlock = async (e) => {
    e.preventDefault()
    if (!pin.trim()) return
    setBusy(true)
    setError('')
    try {
      const res = await openDb(pin.trim())
      tokenRef.current = res.token
      setToken(res.token)
      setLeft(res.expires_in)
      setPin('')
      await load(res.token)
    } catch (err) {
      setError(err.message)
      setBusy(false)
      if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        gsap.fromTo(card.current, { x: 0 }, { keyframes: { x: [-10, 9, -6, 4, 0] }, duration: 0.45 })
      }
    }
  }

  // Activity log: filtered on the server, refetched when a filter changes (search waits for a pause)
  useEffect(() => {
    if (!token || tab !== 'actions') return
    let live = true
    const id = setTimeout(
      () => {
        getDbActions(token, filters)
          .then((res) => live && setActivity(res))
          .catch((err) => live && setError(err.message))
      },
      filters.q ? 250 : 0,
    )
    return () => {
      live = false
      clearTimeout(id)
    }
  }, [token, tab, filters])

  const loadOlder = async () => {
    const last = activity?.items.at(-1)
    if (!last) return
    setLoadingMore(true)
    try {
      const res = await getDbActions(token, { ...filters, before: last.id })
      setActivity((a) => ({ items: [...a.items, ...res.items], more: res.more }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingMore(false)
    }
  }

  const remove = async (id) => {
    if (armed !== id) {
      setArmed(id)
      return
    }
    setArmed(null)
    try {
      await (tab === 'facts' ? deleteDbFact : deleteDbNote)(token, id)
      await load(token)
    } catch (err) {
      setError(err.message)
    }
  }

  const counts = records?.counts
  const rows = (tab === 'actions' ? activity?.items : records?.[tab]) ?? []
  const filtered = Boolean(filters.group || filters.outcome || filters.q)

  return (
    <div ref={root} className="fixed inset-0 z-40 flex items-center justify-center bg-abyss/80 p-4 backdrop-blur-md">
      <section
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-labelledby="db-title"
        className={`glass flex max-h-[88dvh] w-full flex-col overflow-hidden rounded-3xl shadow-[0_0_80px_-20px_rgba(220,20,60,0.6)] ${
          token ? 'max-w-4xl' : 'max-w-sm'
        }`}
      >
        <header className="flex items-center gap-3 border-b border-scar/40 px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-scar/60 text-ember">
            <Icon name="database" size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="db-title" className="text-[16px] font-semibold text-bone">
              Database
            </h2>
            <p className="truncate text-[12px] text-smoke">backend/nightmare.db</p>
          </div>
          {token && (
            <span className={`text-[12px] ${left <= 60 ? 'text-bile' : 'text-ash'}`} aria-live="polite">
              Closes in {clock(Math.max(left, 0))}
            </span>
          )}
          <button
            type="button"
            onClick={close}
            aria-label="Close database"
            title="Close database (Esc)"
            className="grid h-8 w-8 place-items-center rounded-full border border-scar/60 text-ash hover:text-bone"
          >
            <Icon name="close" size={15} />
          </button>
        </header>

        {!token ? (
          <form onSubmit={unlock} className="flex flex-col gap-3 p-5">
            <p className="text-[13px] leading-relaxed text-ash">
              Type your PIN to open the database. It is never spoken aloud or saved in the conversation.
            </p>
            <label htmlFor="db-pin" className="sr-only">
              PIN
            </label>
            <input
              id="db-pin"
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="PIN"
              autoFocus
              autoComplete="off"
              aria-invalid={Boolean(error)}
              className="rounded-xl border border-scar/70 bg-abyss/70 px-4 py-3 text-center text-[15px] tracking-[0.3em] text-bone outline-none placeholder:tracking-normal placeholder:text-smoke focus:border-ember"
            />
            {error && <p className="text-center text-[12px] text-ember">{error}</p>}
            <button
              type="submit"
              disabled={busy || !pin.trim()}
              className="rounded-xl bg-gradient-to-b from-crimson to-[#9e0d2b] px-4 py-3 text-[14px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(220,20,60,0.8)] hover:brightness-110 disabled:opacity-40"
            >
              {busy ? 'Checking…' : 'Open database'}
            </button>
          </form>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1 border-b border-scar/40 px-3 py-2" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.key}
                  onClick={() => setTab(t.key)}
                  className={`rounded-xl px-3 py-1.5 text-[13px] ${
                    tab === t.key ? 'bg-scar/50 text-bone' : 'text-ash hover:text-bone'
                  }`}
                >
                  {t.label}
                  {counts && <span className="ml-1.5 text-smoke">{counts[t.key]}</span>}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  load(token)
                  if (tab === 'actions') setFilters((f) => ({ ...f })) // refetch the log too
                }}
                disabled={busy}
                className="ml-auto flex items-center gap-1.5 rounded-xl border border-scar/60 px-3 py-1.5 text-[12px] text-ash hover:text-bone disabled:opacity-40"
              >
                <Icon name="refresh" size={13} /> Refresh
              </button>
            </div>
            {error && <p className="px-5 pt-3 text-[12px] text-ember">{error}</p>}
            {tab === 'llm_calls' && <p className="px-5 pt-3 text-[11px] text-smoke">Showing the latest 200 rows.</p>}
            {tab === 'actions' && (
              <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
                <div className="flex flex-wrap gap-1" role="group" aria-label="Show">
                  {GROUPS.map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      aria-pressed={filters.group === g.key}
                      onClick={() => setFilters((f) => ({ ...f, group: g.key }))}
                      className={`rounded-lg px-2.5 py-1 text-[12px] ${
                        filters.group === g.key ? 'bg-scar/60 text-bone' : 'text-ash hover:text-bone'
                      }`}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
                <select
                  aria-label="Result"
                  value={filters.outcome}
                  onChange={(e) => setFilters((f) => ({ ...f, outcome: e.target.value }))}
                  className="rounded-lg border border-scar/60 bg-abyss/70 px-2 py-1 text-[12px] text-bone outline-none focus:border-ember"
                >
                  <option value="">Any result</option>
                  <option value="problems">Problems only</option>
                  <option value="ok">OK only</option>
                </select>
                <input
                  type="search"
                  value={filters.q}
                  onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                  placeholder="Search…"
                  aria-label="Search the activity log"
                  className="min-w-0 flex-1 rounded-lg border border-scar/60 bg-abyss/70 px-2.5 py-1 text-[12px] text-bone outline-none placeholder:text-smoke focus:border-ember sm:max-w-[16rem]"
                />
              </div>
            )}

            <div className="scroll-thin min-h-0 flex-1 overflow-auto px-2 pb-3 pt-1">
              {!records || (tab === 'actions' && !activity) ? (
                <div className="space-y-2 p-3">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="shimmer h-8 rounded-lg" />
                  ))}
                </div>
              ) : rows.length === 0 ? (
                <p className="p-6 text-center text-[13px] text-ash">
                  {tab === 'actions' && filtered ? 'Nothing matches these filters.' : 'Nothing stored here yet.'}
                </p>
              ) : (
                <table className="w-full border-separate border-spacing-0 text-[12.5px]">
                  {tab === 'notes' && (
                    <>
                      <thead>
                        <tr>
                          <Th className="w-12">#</Th>
                          <Th>Reminder</Th>
                          <Th className="w-36">Added</Th>
                          <Th className="w-20">Status</Th>
                          <Th className="w-28" />
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((n) => (
                          <tr key={n.id} className="text-bone even:bg-scab/40">
                            <td className="px-3 py-2 text-ember">{n.id}</td>
                            <td className="break-words px-3 py-2">{n.text}</td>
                            <td className="px-3 py-2 text-ash">{stamp(n.ts)}</td>
                            <td className={`px-3 py-2 ${n.done ? 'text-smoke' : 'text-ember'}`}>{n.done ? 'Done' : 'Active'}</td>
                            <td className="px-3 py-2 text-right">
                              <button
                                type="button"
                                onClick={() => remove(n.id)}
                                onBlur={() => setArmed((a) => (a === n.id ? null : a))}
                                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${
                                  armed === n.id
                                    ? 'border-ember bg-crimson/30 text-white'
                                    : 'border-scar/60 text-ash hover:border-ember/60 hover:text-bone'
                                }`}
                              >
                                <Icon name="trash" size={12} />
                                {armed === n.id ? 'Click to confirm' : 'Delete'}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </>
                  )}
                  {tab === 'facts' && (
                    <>
                      <thead>
                        <tr>
                          <Th className="w-12">#</Th>
                          <Th>Remembered (say "forget that ...")</Th>
                          <Th className="w-36">Added</Th>
                          <Th className="w-28" />
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((n) => (
                          <tr key={n.id} className="text-bone even:bg-scab/40">
                            <td className="px-3 py-2 text-ember">{n.id}</td>
                            <td className="break-words px-3 py-2">{n.text}</td>
                            <td className="px-3 py-2 text-ash">{stamp(n.ts)}</td>
                            <td className="px-3 py-2 text-right">
                              <button
                                type="button"
                                onClick={() => remove(n.id)}
                                onBlur={() => setArmed((a) => (a === n.id ? null : a))}
                                className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${
                                  armed === n.id
                                    ? 'border-ember bg-crimson/30 text-white'
                                    : 'border-scar/60 text-ash hover:border-ember/60 hover:text-bone'
                                }`}
                              >
                                <Icon name="trash" size={12} />
                                {armed === n.id ? 'Click to confirm' : 'Delete'}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </>
                  )}
                  {tab === 'actions' && (
                    <>
                      <thead>
                        <tr>
                          <Th className="w-36">When</Th>
                          <Th className="w-36">Action</Th>
                          <Th>Detail</Th>
                          <Th className="w-28">Result</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((a) => (
                          <tr key={a.id} className="text-bone even:bg-scab/40">
                            <td className="px-3 py-2 text-ash">{stamp(a.ts)}</td>
                            <td className="px-3 py-2">
                              {a.kind.replaceAll('_', ' ')}
                              {a.detail.startsWith('remote:') && (
                                <span className="ml-1.5 rounded-full border border-bile/40 px-1.5 py-px text-[10px] text-bile">
                                  Phone
                                </span>
                              )}
                            </td>
                            <td className="max-w-[28rem] truncate px-3 py-2 text-ash" title={a.detail}>
                              {a.detail}
                            </td>
                            <td className={`px-3 py-2 ${PROBLEM_RE.test(a.status) ? 'text-bile' : 'text-ash'}`}>
                              {a.status.replaceAll('_', ' ')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </>
                  )}
                  {tab === 'llm_calls' && (
                    <>
                      <thead>
                        <tr>
                          <Th className="w-36">When</Th>
                          <Th>Model</Th>
                          <Th className="w-20">Result</Th>
                          <Th className="w-24">Time</Th>
                          <Th className="w-32">Characters in / out</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((c, i) => (
                          <tr key={i} className="text-bone even:bg-scab/40">
                            <td className="px-3 py-2 text-ash">{stamp(c.ts)}</td>
                            <td className="px-3 py-2">{c.provider}</td>
                            <td className={`px-3 py-2 ${c.ok ? 'text-ash' : 'text-bile'}`}>{c.ok ? 'OK' : 'Failed'}</td>
                            <td className="px-3 py-2 text-ash">{(c.duration_ms / 1000).toFixed(1)}s</td>
                            <td className="px-3 py-2 text-ash">
                              {c.chars_in} / {c.chars_out}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </>
                  )}
                </table>
              )}
              {tab === 'actions' && activity?.more && (
                <div className="flex justify-center p-3">
                  <button
                    type="button"
                    onClick={loadOlder}
                    disabled={loadingMore}
                    className="rounded-xl border border-scar/60 px-3 py-1.5 text-[12px] text-ash hover:text-bone disabled:opacity-40"
                  >
                    {loadingMore ? 'Loading…' : `Load older (showing ${rows.length})`}
                  </button>
                </div>
              )}
            </div>
            <p className="border-t border-scar/40 px-5 py-2.5 text-[11px] text-smoke">
              Say “database close”, press Esc, or use the close button. Access ends by itself when the timer runs out.
            </p>
          </>
        )}
      </section>
    </div>
  )
}
