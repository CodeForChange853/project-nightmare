import { useEffect, useMemo, useRef, useState } from 'react'
import AnswerCard from './AnswerCard'
import Composer from './Composer'
import { Selected } from './Dossier'
import EyeButton from './EyeButton'
import Icon from './Icon'
import Terminal from './Terminal'

export const PHONE_TABS = [
  { key: 'talk', label: 'Talk', icon: 'mic' },
  { key: 'projects', label: 'Projects', icon: 'folder' },
  { key: 'reminders', label: 'Reminders', icon: 'bell' },
  { key: 'chat', label: 'Chat', icon: 'log' },
]

function TalkTab({ mode, title, caption, canTalk, onPressStart, onPressEnd, answer, asked, busy, elapsed, speaking, onSpeak,
  onStop, asks, disabled, onRun, onMore }) {
  return (
    <div className="flex flex-col items-center gap-4 px-4 pb-4 pt-1">
      <EyeButton
        mode={mode}
        canTalk={canTalk}
        onPressStart={onPressStart}
        onPressEnd={onPressEnd}
        style={{ width: 'min(58vw, 230px)', aspectRatio: '1' }}
      />
      <div className="-mt-1 text-center" aria-live="polite">
        <p className="font-display text-[22px] font-bold uppercase leading-none tracking-[0.16em] text-bone">{title}</p>
        <p className="mt-1.5 text-[13px] text-ash">
          {caption}
          {mode === 'listening' && <span className="caret ml-0.5 text-ember">▌</span>}
        </p>
      </div>
      <AnswerCard
        className="max-h-[38dvh] w-full"
        entry={answer}
        asked={asked}
        busy={busy}
        elapsed={elapsed}
        speaking={speaking}
        onSpeak={onSpeak}
        onStop={onStop}
        onMore={answer ? onMore : null}
        empty="Hold the eye and ask anything, like “progress of bims”, or tap a quick ask below."
      />
      <div className="grid w-full grid-cols-2 gap-2">
        {asks.map((a) => (
          <button
            key={a.id}
            type="button"
            disabled={disabled}
            onClick={() => onRun(a.actions[0].command)}
            className="tile min-h-12 rounded-xl px-3 py-2.5 text-left text-[13px] leading-snug text-bone disabled:opacity-40"
          >
            {a.title}
          </button>
        ))}
      </div>
    </div>
  )
}

function ProjectsTab({ items, readonly, disabled, onRun, openId, onOpen, onBack }) {
  const [query, setQuery] = useState('')
  const open = items.find((i) => i.id === openId)
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? items.filter((i) => i.title.toLowerCase().includes(q)) : items
  }, [items, query])

  if (open) {
    return (
      <div className="flex flex-col gap-3 px-4 pb-4 pt-1">
        <button
          type="button"
          onClick={onBack}
          className="flex min-h-11 items-center gap-1 self-start rounded-xl pr-3 text-[14px] text-ash hover:text-bone"
        >
          <Icon name="back" size={18} /> Projects
        </button>
        <Selected item={open} readonly={readonly} disabled={disabled} onRun={onRun} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 px-4 pb-4 pt-1">
      <label className="flex min-h-11 items-center gap-2 rounded-xl border border-scar/60 bg-abyss/60 px-3 focus-within:border-ember/70">
        <Icon name="search" size={16} className="text-smoke" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${items.length} projects`}
          aria-label="Search projects"
          className="min-w-0 flex-1 bg-transparent py-2 text-[15px] text-bone outline-none placeholder:text-smoke"
        />
      </label>
      {shown.length === 0 && <p className="px-1 text-[14px] text-smoke">No project matches “{query}”.</p>}
      <ul className="flex flex-col gap-2">
        {shown.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onOpen(item.id)}
              className="tile flex min-h-14 w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-left"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] text-bone">{item.title}</span>
                <span className={`block truncate text-[12px] ${item.tone === 'warn' ? 'text-bile' : 'text-smoke'}`}>{item.tag}</span>
              </span>
              <Icon name="chevron" size={16} className="shrink-0 text-smoke" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RemindersTab({ items, disabled, onRun }) {
  return (
    <div className="flex flex-col gap-2 px-4 pb-4 pt-1">
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-scar/50 p-4 text-[14px] leading-relaxed text-ash">
          No open reminders. Hold the eye and say “remind me to …” to add one.
        </p>
      ) : (
        items.map((item) => (
          <article key={item.id} className="tile flex items-start gap-3 rounded-xl p-3.5">
            <div className="min-w-0 flex-1">
              <p className="break-words text-[15px] leading-snug text-bone">{item.title}</p>
              <p className="mt-1 text-[12px] text-smoke">
                {item.tag} · {item.facts?.[0]?.value}
              </p>
            </div>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onRun(item.actions[0].command)}
              className="flex min-h-11 shrink-0 items-center gap-1 rounded-xl border border-scar/70 px-3 text-[13px] text-ash hover:text-bone disabled:opacity-40"
            >
              <Icon name="check" size={15} /> Done
            </button>
          </article>
        ))
      )}
    </div>
  )
}

/**
 * Phone layout: one screen per tab with a thumb-reach tab bar, instead of one long scrolling page.
 * Opening a project pushes a history entry, so Android's back gesture closes it instead of leaving.
 */
export default function PhoneView({ tab, onTab, categories, entries, unread, readonly, disabled, onRun, talk, composer, busy, elapsed, onSpeak }) {
  const byKey = Object.fromEntries(categories.map((c) => [c.key, c]))
  const [openId, setOpenId] = useState(null)
  const scroller = useRef(null)

  useEffect(() => {
    const onPop = () => setOpenId(null)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const openProject = (id) => {
    window.history.pushState({ nightmare: 'project' }, '')
    setOpenId(id)
    scroller.current?.scrollTo({ top: 0 })
  }
  const closeProject = () => {
    if (window.history.state?.nightmare === 'project') window.history.back() // popstate clears openId
    else setOpenId(null)
  }

  const counts = { reminders: byKey.reminders?.items.length || 0, chat: unread }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <main ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto" aria-label={PHONE_TABS.find((t) => t.key === tab)?.label}>
        {tab === 'talk' && (
          <TalkTab {...talk} asks={byKey.asks?.items ?? []} disabled={disabled} onRun={onRun} onMore={() => onTab('chat')} />
        )}
        {tab === 'projects' && (
          <ProjectsTab
            items={byKey.projects?.items ?? []}
            readonly={readonly}
            disabled={disabled}
            onRun={onRun}
            openId={openId}
            onOpen={openProject}
            onBack={closeProject}
          />
        )}
        {tab === 'reminders' && <RemindersTab items={byKey.reminders?.items ?? []} disabled={disabled} onRun={onRun} />}
        {tab === 'chat' && (
          <div className="flex h-full min-h-0 flex-col">
            <Terminal entries={entries} busy={busy} elapsed={elapsed} onSpeak={onSpeak} />
          </div>
        )}
      </main>

      {tab === 'chat' && <Composer {...composer} />}

      <nav
        aria-label="Sections"
        className="glass grid grid-cols-4 border-t border-scar/50 pb-[env(safe-area-inset-bottom)]"
      >
        {PHONE_TABS.map((t) => {
          const active = t.key === tab
          const badge = counts[t.key]
          return (
            <button
              key={t.key}
              type="button"
              aria-current={active ? 'page' : undefined}
              onClick={() => onTab(t.key)}
              className={`relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${
                active ? 'text-ember' : 'text-ash'
              }`}
            >
              {active && <span className="absolute inset-x-5 top-0 h-0.5 rounded-full bg-crimson" />}
              <Icon name={t.icon} size={21} />
              {t.label}
              {badge > 0 && (
                <span className="absolute right-[22%] top-1.5 grid h-[17px] min-w-[17px] place-items-center rounded-full bg-crimson px-1 text-[10px] font-semibold text-white">
                  {badge}
                </span>
              )}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
