import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { checkAppsEntry, closeSettings, getAppsConfig, openSettings, saveAppsConfig } from '../api'
import Icon from './Icon'

const KINDS = [
  { key: 'apps', label: 'Apps', noun: 'app', check: 'app' },
  { key: 'tasks', label: 'Tasks', noun: 'task', check: 'task' },
]
const ID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/
const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
const programName = (p = '') =>
  p
    .trim()
    .split(/[\\/]/)
    .pop()
    .toLowerCase()
    .replace(/\.(exe|cmd|bat|com)$/, '')

// key order doesn't matter to the backend, so compare with sorted keys
const stable = (v) =>
  Array.isArray(v)
    ? `[${v.map(stable).join(',')}]`
    : v && typeof v === 'object'
      ? `{${Object.keys(v)
          .sort()
          .map((k) => `${JSON.stringify(k)}:${stable(v[k])}`)
          .join(',')}}`
      : JSON.stringify(v)

function changesBetween(saved, draft) {
  const out = []
  for (const { key, noun } of KINDS) {
    const before = saved?.[key] ?? {}
    const after = draft?.[key] ?? {}
    for (const id of Object.keys(after)) {
      if (!(id in before)) out.push({ key, id, what: `add ${noun}` })
      else if (stable(before[id]) !== stable(after[id])) out.push({ key, id, what: `change ${noun}` })
    }
    for (const id of Object.keys(before)) if (!(id in after)) out.push({ key, id, what: `remove ${noun}` })
  }
  return out
}

// what goes to the server: untouched entries exactly as loaded, edited ones without blank lines
function cleanTable(saved, draft) {
  const out = {}
  for (const [id, spec] of Object.entries(draft)) {
    if (spec === saved[id]) {
      out[id] = spec
      continue
    }
    const clean = { ...spec }
    clean.argv = (spec.argv ?? []).map((a) => a.trim()).filter(Boolean)
    if (spec.aliases) clean.aliases = spec.aliases.map((a) => a.trim()).filter(Boolean)
    if (spec.timeout !== undefined) clean.timeout = Number.parseInt(spec.timeout, 10) || 0
    if (!spec.project) delete clean.project
    if (!spec.project_arg) delete clean.project_flag
    out[id] = clean
  }
  return out
}

function Field({ label, hint, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-ash">{label}</span>
      {children}
      {hint && <span className="text-[11px] leading-snug text-smoke">{hint}</span>}
    </label>
  )
}

const inputCls =
  'rounded-xl border border-scar/70 bg-abyss/70 px-3 py-2 text-[13px] text-bone outline-none placeholder:text-smoke focus:border-ember disabled:opacity-50'

function Toggle({ checked, onChange, disabled, children, note }) {
  return (
    <label className={`flex items-start gap-2.5 text-[13px] ${disabled ? 'text-smoke' : 'text-bone'}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[#dc143c]"
      />
      <span>
        {children}
        {note && <span className="mt-0.5 block text-[11px] text-smoke">{note}</span>}
      </span>
    </label>
  )
}

function EntryForm({ kind, id, spec, saved, projects, shells, onChange, onCheck, check, checking }) {
  const set = (field, value) => onChange({ ...spec, [field]: value })
  const argv = spec.argv ?? []
  const touched = spec !== saved
  const shell = shells.has(programName(argv[0]))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-2">
        <h3 className="font-mono text-[15px] text-bone">{id}</h3>
        {!saved && <span className="rounded-full bg-crimson/25 px-2 py-0.5 text-[11px] text-ember">new</span>}
        {saved && touched && <span className="rounded-full bg-bile/15 px-2 py-0.5 text-[11px] text-bile">edited</span>}
      </div>

      <Field label="Name shown in Nightmare">
        <input className={inputCls} value={spec.label ?? ''} maxLength={60} onChange={(e) => set('label', e.target.value)} />
      </Field>

      <Field
        label="Spoken names"
        hint={`Comma separated. Saying â€œ${kind.key === 'apps' ? 'open' : 'run'} ${spec.aliases?.[0] || id}â€ picks this ${kind.noun}.`}
      >
        <input
          className={inputCls}
          value={(spec.aliases ?? []).join(', ')}
          onChange={(e) => set('aliases', e.target.value.split(','))}
          placeholder={`e.g. ${id.replaceAll('-', ' ')}`}
        />
      </Field>

      <Field label="Program" hint="A name on PATH (notepad.exe, code, npm) or a full path. Nothing goes through a shell.">
        <input
          className={`${inputCls} font-mono`}
          value={argv[0] ?? ''}
          spellCheck={false}
          onChange={(e) => set('argv', [e.target.value, ...argv.slice(1)])}
        />
      </Field>

      <Field label="Arguments" hint="One per line, passed exactly as written.">
        <textarea
          className={`${inputCls} min-h-[72px] resize-y font-mono`}
          value={argv.slice(1).join('\n')}
          spellCheck={false}
          onChange={(e) => set('argv', [argv[0] ?? '', ...e.target.value.split('\n')])}
        />
      </Field>

      {kind.key === 'apps' ? (
        <>
          <Toggle checked={Boolean(spec.project_arg)} onChange={(v) => set('project_arg', v)}>
            Can open a project (â€œopen bims in {spec.aliases?.[0] || id}â€)
          </Toggle>
          {spec.project_arg && (
            <Field label="Flag before the folder (optional)" hint="Only if the program needs one, e.g. -d for Windows Terminal.">
              <input
                className={`${inputCls} w-40 font-mono`}
                value={spec.project_flag ?? ''}
                onChange={(e) => set('project_flag', e.target.value)}
              />
            </Field>
          )}
          <Toggle
            checked={shell || Boolean(spec.confirm)}
            disabled={shell}
            onChange={(v) => set('confirm', v)}
            note={shell ? `${programName(argv[0])} can run any command, so it always asks first.` : null}
          >
            Ask before opening
          </Toggle>
        </>
      ) : (
        <>
          <Field label="Run inside project" hint="The folder the command starts in. None means the Desktop.">
            <select className={inputCls} value={spec.project ?? ''} onChange={(e) => set('project', e.target.value)}>
              <option value="">None (Desktop)</option>
              {projects.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
              {spec.project && !projects.includes(spec.project) && <option value={spec.project}>{spec.project} (missing)</option>}
            </select>
          </Field>
          <Toggle checked={Boolean(spec.wait)} onChange={(v) => set('wait', v)}>
            Wait for it and read out the result
          </Toggle>
          {spec.wait && (
            <Field label="Stop after (seconds)">
              <input
                type="number"
                min={1}
                max={600}
                className={`${inputCls} w-32`}
                value={spec.timeout ?? 60}
                onChange={(e) => set('timeout', e.target.value)}
              />
            </Field>
          )}
          <Toggle
            checked={touched || spec.confirm !== false}
            disabled
            onChange={() => {}}
            note={
              touched
                ? 'Tasks added or changed in Settings always ask before running.'
                : spec.confirm === false
                  ? 'Runs without asking: set by hand in apps.json. Editing it here turns asking on.'
                  : null
            }
          >
            Ask before running
          </Toggle>
        </>
      )}

      <div className="flex flex-col gap-2 rounded-2xl border border-scar/50 bg-abyss/40 p-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCheck}
            disabled={checking || !argv[0]?.trim()}
            className="flex items-center gap-1.5 rounded-lg border border-scar/60 px-2.5 py-1 text-[12px] text-ash hover:text-bone disabled:opacity-40"
          >
            <Icon name="check" size={13} /> {checking ? 'Checkingâ€¦' : 'Check'}
          </button>
          <span className="text-[11px] text-smoke">Looks the program up. Nothing is run.</span>
        </div>
        {check && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
            <dt className="text-smoke">Program</dt>
            <dd className={`break-all font-mono ${check.found ? 'text-bone' : 'text-bile'}`}>{check.found || 'not found on PATH'}</dd>
            <dt className="text-smoke">Command</dt>
            <dd className="break-all font-mono text-bone">{check.command_line}</dd>
            {'folder' in check && (
              <>
                <dt className="text-smoke">Folder</dt>
                <dd className="break-all text-bone">{check.folder || 'â€”'}</dd>
              </>
            )}
            <dt className="text-smoke">Asks first</dt>
            <dd className="text-bone">{check.asks_first ? 'Yes' : 'No, it runs as soon as you ask'}</dd>
            {check.note && <dd className="col-span-2 text-bile">{check.note}</dd>}
          </dl>
        )}
      </div>
    </div>
  )
}

/**
 * "open settings" -> type the PIN -> edit apps.json. Voice can open this panel but every change is
 * typed and clicked here. The token lives only in this component, like the database viewer's.
 */
export default function SettingsPanel({ onClose }) {
  const root = useRef(null)
  const card = useRef(null)
  const tokenRef = useRef(null)
  const [token, setToken] = useState(null)
  const [left, setLeft] = useState(0)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [errors, setErrors] = useState([])
  const [stale, setStale] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(null) // what the server has: {apps, tasks, version, projects, shells}
  const [draft, setDraft] = useState(null)
  const [tab, setTab] = useState('apps')
  const [selected, setSelected] = useState(null)
  const [newId, setNewId] = useState(null) // text of the "new id" box while adding
  const [armed, setArmed] = useState(null) // 'close' | `delete:${id}` waiting for a second click
  const [result, setResult] = useState(null)
  const [checks, setChecks] = useState({})
  const [checking, setChecking] = useState(false)

  const kind = KINDS.find((k) => k.key === tab)
  const pending = useMemo(() => (saved && draft ? changesBetween(saved, draft) : []), [saved, draft])
  const shells = useMemo(() => new Set(saved?.shells ?? []), [saved])

  const finish = useCallback(() => {
    const t = tokenRef.current
    tokenRef.current = null
    if (t) closeSettings(t).catch(() => {})
    onClose()
  }, [onClose])

  const close = useCallback(() => {
    if (pending.length && armed !== 'close') {
      setArmed('close')
      return
    }
    finish()
  }, [pending.length, armed, finish])

  useEffect(
    () => () => {
      if (tokenRef.current) closeSettings(tokenRef.current).catch(() => {})
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

  useEffect(() => {
    if (!token) return
    const id = setInterval(() => setLeft((s) => s - 1), 1000)
    return () => clearInterval(id)
  }, [token])
  useEffect(() => {
    if (token && left <= 0) finish()
  }, [token, left, finish])

  const load = useCallback(async (t) => {
    setBusy(true)
    setError('')
    setErrors([])
    setStale(false)
    try {
      const data = await getAppsConfig(t)
      setSaved(data)
      setDraft({ apps: data.apps, tasks: data.tasks })
      setSelected((s) => s ?? Object.keys(data.apps)[0] ?? null)
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
      const res = await openSettings(pin.trim())
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

  const switchTab = (key) => {
    setTab(key)
    setSelected(Object.keys(draft?.[key] ?? {})[0] ?? null)
    setNewId(null)
    setArmed(null)
  }

  const updateEntry = (id, spec) => {
    setDraft((d) => ({ ...d, [tab]: { ...d[tab], [id]: spec } }))
    setChecks((c) => ({ ...c, [`${tab}:${id}`]: undefined }))
    setResult(null)
    setArmed(null)
  }

  const addEntry = (e) => {
    e.preventDefault()
    const id = (newId ?? '').trim()
    if (!ID_RE.test(id) || id in draft[tab]) return
    const spec =
      tab === 'apps'
        ? { label: '', argv: [''], aliases: [id.replaceAll('-', ' ')] }
        : { label: '', argv: [''], aliases: [id.replaceAll('-', ' ')], wait: false, timeout: 60, confirm: true }
    setDraft((d) => ({ ...d, [tab]: { ...d[tab], [id]: spec } }))
    setSelected(id)
    setNewId(null)
    setResult(null)
  }

  const removeEntry = (id) => {
    if (armed !== `delete:${id}`) {
      setArmed(`delete:${id}`)
      return
    }
    setArmed(null)
    setDraft((d) => {
      const table = { ...d[tab] }
      delete table[id]
      return { ...d, [tab]: table }
    })
    setSelected(Object.keys(draft[tab]).find((k) => k !== id) ?? null)
    setResult(null)
  }

  const runCheck = async () => {
    const spec = draft[tab][selected]
    setChecking(true)
    try {
      const res = await checkAppsEntry(token, kind.check, {
        ...spec,
        argv: (spec.argv ?? []).map((a) => a.trim()).filter(Boolean),
      })
      setChecks((c) => ({ ...c, [`${tab}:${selected}`]: res }))
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }

  const save = async () => {
    setBusy(true)
    setError('')
    setErrors([])
    setResult(null)
    try {
      const res = await saveAppsConfig(token, {
        apps: cleanTable(saved.apps, draft.apps),
        tasks: cleanTable(saved.tasks, draft.tasks),
        version: saved.version,
      })
      setSaved((s) => ({ ...s, apps: res.apps, tasks: res.tasks, version: res.version }))
      setDraft({ apps: res.apps, tasks: res.tasks })
      setResult({ changes: res.changes, notes: res.notes })
    } catch (err) {
      setError(err.message)
      setErrors(err.errors ?? [])
      setStale(err.status === 409)
    } finally {
      setBusy(false)
    }
  }

  const entries = draft ? Object.entries(draft[tab]) : []
  const current = draft && selected != null ? draft[tab][selected] : null
  const idProblem =
    newId == null || newId === ''
      ? ''
      : !ID_RE.test(newId.trim())
        ? 'Lowercase letters, digits and dashes only'
        : newId.trim() in (draft?.[tab] ?? {})
          ? 'That id is taken'
          : ''

  return (
    <div ref={root} className="fixed inset-0 z-40 flex items-center justify-center bg-abyss/80 p-4 backdrop-blur-md">
      <section
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className={`glass flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-3xl shadow-[0_0_80px_-20px_rgba(220,20,60,0.6)] ${
          token ? 'max-w-5xl' : 'max-w-sm'
        }`}
      >
        <header className="flex items-center gap-3 border-b border-scar/40 px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-scar/60 text-ember">
            <Icon name="sliders" size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="settings-title" className="text-[16px] font-semibold text-bone">
              Settings
            </h2>
            <p className="truncate text-[12px] text-smoke">Apps and tasks Nightmare may open or run (backend/apps.json)</p>
          </div>
          {token && (
            <span className={`hidden text-[12px] sm:inline ${left <= 60 ? 'text-bile' : 'text-ash'}`} aria-live="polite">
              Locks in {clock(Math.max(left, 0))}
            </span>
          )}
          <button
            type="button"
            onClick={close}
            aria-label="Close settings"
            title="Close settings (Esc)"
            className={`grid h-8 place-items-center rounded-full border px-2 text-[12px] ${
              armed === 'close' ? 'border-ember bg-crimson/30 text-white' : 'w-8 border-scar/60 text-ash hover:text-bone'
            }`}
          >
            {armed === 'close' ? 'Discard changes?' : <Icon name="close" size={15} />}
          </button>
        </header>

        {!token ? (
          <form onSubmit={unlock} className="flex flex-col gap-3 p-5">
            <p className="text-[13px] leading-relaxed text-ash">
              Type your PIN to change which apps and tasks Nightmare can open or run. It is never spoken aloud.
            </p>
            <label htmlFor="settings-pin" className="sr-only">
              PIN
            </label>
            <input
              id="settings-pin"
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
              {busy ? 'Checkingâ€¦' : 'Open settings'}
            </button>
          </form>
        ) : !draft ? (
          <div className="space-y-2 p-5">
            {error ? <p className="text-[13px] text-ember">{error}</p> : [0, 1, 2].map((i) => <div key={i} className="shimmer h-9 rounded-lg" />)}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1 border-b border-scar/40 px-3 py-2" role="tablist">
              {KINDS.map((k) => (
                <button
                  key={k.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === k.key}
                  onClick={() => switchTab(k.key)}
                  className={`rounded-xl px-3 py-1.5 text-[13px] ${tab === k.key ? 'bg-scar/50 text-bone' : 'text-ash hover:text-bone'}`}
                >
                  {k.label}
                  <span className="ml-1.5 text-smoke">{Object.keys(draft[k.key]).length}</span>
                </button>
              ))}
              <button
                type="button"
                onClick={() => setNewId('')}
                className="ml-auto flex items-center gap-1.5 rounded-xl border border-scar/60 px-3 py-1.5 text-[12px] text-ash hover:text-bone"
              >
                <Icon name="plus" size={13} /> Add {kind.noun}
              </button>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[230px_minmax(0,1fr)]">
              <div className="scroll-thin max-h-[30dvh] overflow-y-auto border-b border-scar/40 p-2 md:max-h-none md:border-b-0 md:border-r">
                {newId != null && (
                  <form onSubmit={addEntry} className="mb-2 flex flex-col gap-1 rounded-xl border border-ember/50 p-2">
                    <input
                      autoFocus
                      value={newId}
                      onChange={(e) => setNewId(e.target.value.toLowerCase())}
                      onKeyDown={(e) => e.key === 'Escape' && (e.stopPropagation(), setNewId(null))}
                      placeholder={`new ${kind.noun} id, e.g. ${tab === 'apps' ? 'spotify' : 'bims-build'}`}
                      aria-label={`New ${kind.noun} id`}
                      className={`${inputCls} font-mono`}
                    />
                    {idProblem && <span className="text-[11px] text-bile">{idProblem}</span>}
                    <div className="flex gap-1.5">
                      <button
                        type="submit"
                        disabled={!newId.trim() || Boolean(idProblem)}
                        className="flex-1 rounded-lg bg-crimson/80 px-2 py-1 text-[12px] text-white disabled:opacity-40"
                      >
                        Add
                      </button>
                      <button type="button" onClick={() => setNewId(null)} className="rounded-lg px-2 py-1 text-[12px] text-ash hover:text-bone">
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
                {entries.length === 0 && newId == null && (
                  <p className="p-3 text-[12px] text-smoke">No {tab} yet. Use â€œAdd {kind.noun}â€.</p>
                )}
                <ul className="flex flex-col gap-1">
                  {entries.map(([id, spec]) => {
                    const status = pending.find((p) => p.key === tab && p.id === id)
                    return (
                      <li key={id}>
                        <button
                          type="button"
                          onClick={() => {
                            setSelected(id)
                            setArmed(null)
                          }}
                          className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left ${
                            id === selected ? 'bg-scar/50 ring-1 ring-crimson/60' : 'hover:bg-scab/60'
                          }`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] text-bone">{spec.label || id}</span>
                            <span className="block truncate font-mono text-[11px] text-smoke">{id}</span>
                          </span>
                          {status && <span className="h-2 w-2 shrink-0 rounded-full bg-bile" title={status.what} />}
                        </button>
                      </li>
                    )
                  })}
                </ul>
                {(() => {
                  const removed = pending.filter((p) => p.key === tab && p.what.startsWith('remove'))
                  return removed.length > 0 && (
                    <p className="mt-2 px-2 text-[11px] text-bile">Removing on save: {removed.map((r) => r.id).join(', ')}</p>
                  )
                })()}
              </div>

              <div className="scroll-thin min-h-0 overflow-y-auto p-5">
                {current ? (
                  <>
                    <EntryForm
                      kind={kind}
                      id={selected}
                      spec={current}
                      saved={saved[tab][selected]}
                      projects={saved.projects}
                      shells={shells}
                      onChange={(spec) => updateEntry(selected, spec)}
                      onCheck={runCheck}
                      check={checks[`${tab}:${selected}`]}
                      checking={checking}
                    />
                    <button
                      type="button"
                      onClick={() => removeEntry(selected)}
                      onBlur={() => setArmed((a) => (a === `delete:${selected}` ? null : a))}
                      className={`mt-5 inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[12px] ${
                        armed === `delete:${selected}`
                          ? 'border-ember bg-crimson/30 text-white'
                          : 'border-scar/60 text-ash hover:border-ember/60 hover:text-bone'
                      }`}
                    >
                      <Icon name="trash" size={12} />
                      {armed === `delete:${selected}` ? 'Click again to remove' : `Remove this ${kind.noun}`}
                    </button>
                  </>
                ) : (
                  <p className="text-[13px] text-ash">Pick {tab === 'apps' ? 'an app' : 'a task'} on the left, or add one.</p>
                )}
              </div>
            </div>

            <footer className="flex flex-col gap-2 border-t border-scar/40 px-5 py-3">
              {(error || errors.length > 0) && (
                <div className="text-[12px] text-ember" role="alert">
                  {error && <p>{error}</p>}
                  {errors.length > 0 && (
                    <ul className="mt-1 list-disc pl-5">
                      {errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {result && (
                <div className="text-[12px]" role="status">
                  <p className="text-bone">
                    {result.changes.length ? `Saved: ${result.changes.join(', ')}.` : 'Nothing to save.'}
                    {result.changes.length > 0 && <span className="text-smoke"> Works right away, no restart needed.</span>}
                  </p>
                  {result.notes.map((n) => (
                    <p key={n} className="text-bile">
                      {n}
                    </p>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <p className="mr-auto text-[12px] text-ash">
                  {pending.length
                    ? `${pending.length} unsaved change${pending.length > 1 ? 's' : ''}: ${pending.map((p) => `${p.what} ${p.id}`).join(', ')}`
                    : 'No unsaved changes.'}
                </p>
                {stale && (
                  <button
                    type="button"
                    onClick={() => load(token)}
                    className="rounded-xl border border-scar/60 px-3 py-2 text-[13px] text-ash hover:text-bone"
                  >
                    Reload from file
                  </button>
                )}
                <button
                  type="button"
                  disabled={!pending.length || busy}
                  onClick={() => {
                    setDraft({ apps: saved.apps, tasks: saved.tasks })
                    setErrors([])
                    setError('')
                    setArmed(null)
                  }}
                  className="rounded-xl border border-scar/60 px-3 py-2 text-[13px] text-ash hover:text-bone disabled:opacity-40"
                >
                  Undo all
                </button>
                <button
                  type="button"
                  disabled={!pending.length || busy}
                  onClick={save}
                  className="rounded-xl bg-gradient-to-b from-crimson to-[#9e0d2b] px-4 py-2 text-[13px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(220,20,60,0.8)] hover:brightness-110 disabled:opacity-40"
                >
                  {busy ? 'Savingâ€¦' : 'Save changes'}
                </button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  )
}
