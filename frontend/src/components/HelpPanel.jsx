import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { getHelp } from '../api'
import { SLASH_COMMANDS } from '../slashCommands'
import Icon from './Icon'

const ACRONYMS = [
  [/\bpin\b/g, 'PIN'],
  [/\bsqlite\b/g, 'SQLite'],
  [/\bgit\b/g, 'Git'],
  [/\bai\b/g, 'AI'],
  [/\bllm\b/g, 'LLM'],
  [/\brag\b/g, 'RAG'],
  [/\bvs code\b/g, 'VS Code'],
  [/\bcalbayog\b/g, 'Calbayog'],
  [/\bnightmare\b/g, 'Nightmare'],
]

/** "9b. OPEN WEBSITES & SEARCH IN THIS BROWSER" -> "Open websites & search in this browser" */
function tidyTitle(line) {
  let t = line.trim().replace(/^\d+[a-z]?\.\s*/i, '').toLowerCase()
  for (const [re, word] of ACRONYMS) t = t.replace(re, word)
  return t.charAt(0).toUpperCase() + t.slice(1)
}

const isRule = (l) => /^[-=]{10,}\s*$/.test(l)
const isCaps = (l) =>
  l.trim() &&
  l === l.trimStart() &&
  !l.startsWith('-') &&
  /[A-Z]{3}/.test(l) &&
  l.replace(/^\d+[a-z]?\./, '') === l.replace(/^\d+[a-z]?\./, '').toUpperCase()

/** Split nightmare_helper.txt into structured sections: title, purpose, commands, notes, body. */
function parseHelper(text) {
  const lines = text.replace(/\r/g, '').split('\n')
  const sections = []
  let cur = null
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (isRule(line) || /^PROJECT NIGHTMARE|^Last Updated/i.test(line)) continue
    const framed = line.trim() && isRule(lines[i - 1] ?? '') && isRule(lines[i + 1] ?? '')
    if (framed || isCaps(line)) {
      cur = { title: tidyTitle(line), lines: [] }
      sections.push(cur)
    } else if (cur) {
      cur.lines.push(line)
    }
  }

  return sections
    .map((s) => {
      const body = s.lines.join('\n').trim()
      let purpose = ''
      const commands = []
      let notes = ''
      let mode = ''

      for (const rawLine of s.lines) {
        const trimmed = rawLine.trim()
        if (/^purpose:/i.test(trimmed)) {
          mode = 'purpose'
          const after = trimmed.replace(/^purpose:\s*/i, '')
          if (after) purpose = after
          continue
        }
        if (/^(?:voice\s*\/?\s*text\s+commands|commands):/i.test(trimmed)) {
          mode = 'commands'
          continue
        }
        if (/^notes?:/i.test(trimmed)) {
          mode = 'notes'
          const after = trimmed.replace(/^notes?:\s*/i, '')
          if (after) notes = after
          continue
        }

        if (mode === 'purpose') {
          if (trimmed) purpose = purpose ? `${purpose} ${trimmed}` : trimmed
        } else if (mode === 'commands') {
          const m = /"([^"\n]+)"/.exec(trimmed)
          if (m && !commands.includes(m[1])) {
            commands.push(m[1])
          }
        } else if (mode === 'notes') {
          if (trimmed) notes = notes ? `${notes}\n${trimmed}` : trimmed
        }
      }

      return {
        title: s.title,
        purpose: purpose.trim(),
        commands,
        notes: notes.trim(),
        body,
      }
    })
    .filter((s) => s.body)
}

/** Quoted phrases become buttons that run the command; `code` stays monospace. */
function Body({ text, onRun }) {
  const parts = text.split(/("[^"\n]+"|`[^`\n]+`)/g)
  return (
    <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ash">
      {parts.map((p, i) => {
        if (p.startsWith('"') && p.endsWith('"') && p.length > 2) {
          const phrase = p.slice(1, -1)
          if (/[<>]/.test(phrase)) return <span key={i} className="text-bone">{p}</span>
          return (
            <button
              key={i}
              type="button"
              onClick={() => onRun(phrase)}
              title="Run this command"
              className="inline-flex items-center gap-1 rounded-md bg-scar/40 px-1.5 py-0.5 text-bone underline decoration-crimson/60 underline-offset-2 hover:bg-crimson/30 hover:text-white"
            >
              <span className="text-[10px] text-ember">â–¶</span>
              {phrase}
            </button>
          )
        }
        if (p.startsWith('`') && p.endsWith('`')) {
          return (
            <code key={i} className="font-mono text-[11.5px] text-bone">
              {p.slice(1, -1)}
            </code>
          )
        }
        return <span key={i}>{p}</span>
      })}
    </p>
  )
}

export default function HelpPanel({ onClose, onRun }) {
  const root = useRef(null)
  const card = useRef(null)
  const [text, setText] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    getHelp()
      .then((r) => setText(r.text))
      .catch((err) => setError(err.message))
  }, [])

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tl = gsap
      .timeline()
      .from(root.current, { opacity: 0, duration: 0.25 })
      .from(card.current, { y: 35, scale: 0.94, opacity: 0, duration: 0.45, ease: 'back.out(1.15)' }, 0.05)
      .from('.help-section-card', { opacity: 0, y: 15, stagger: 0.03, duration: 0.35, ease: 'power2.out' }, 0.15)
    return () => tl.kill()
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const sections = useMemo(() => (text ? parseHelper(text) : []), [text])
  const q = query.trim().toLowerCase()
  const shown = q ? sections.filter((s) => `${s.title}\n${s.body}`.toLowerCase().includes(q)) : sections

  return (
    <div ref={root} className="fixed inset-0 z-40 flex items-center justify-center bg-abyss/80 p-4 backdrop-blur-md">
      <section
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        className="glass flex max-h-[88dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-scar/60 shadow-2xl"
      >
        <header className="flex items-center gap-3 border-b border-scar/40 bg-abyss/40 px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-scar/60 bg-scar/30 text-ember shadow-sm">
            <Icon name="spark" size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 id="help-title" className="text-[16px] font-semibold text-bone">
                Developer Helper Function
              </h2>
              <span className="rounded-full border border-ember/40 bg-ember/10 px-2 py-0.5 text-[10px] font-mono font-medium text-ember">
                Command Reference
              </span>
            </div>
            <p className="text-[12px] text-smoke">Say any command aloud or click a button to execute it instantly.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close helper"
            className="grid h-8 w-8 place-items-center rounded-full border border-scar/60 text-ash transition hover:border-ember hover:bg-scar/40 hover:text-bone"
          >
            <Icon name="close" size={15} />
          </button>
        </header>

        <div className="border-b border-scar/40 bg-abyss/30 px-5 py-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search commands or purpose (e.g. briefing, weather, voice, rag)..."
            aria-label="Search commands"
            autoFocus
            className="w-full rounded-xl border border-scar/60 bg-abyss/70 px-3.5 py-2 text-[13px] text-bone outline-none placeholder:text-smoke transition focus:border-ember focus:bg-abyss/90"
          />
        </div>

        <div className="scroll-thin min-h-0 flex-1 space-y-3.5 overflow-y-auto p-5">
          {!q && (
            <div className="help-section-card tile rounded-2xl border border-scar/40 p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-[14px] font-medium text-bone">Typed Shortcuts</h3>
                <span className="text-[11px] text-smoke">Type / in chat</span>
              </div>
              <dl className="mt-2.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
                {SLASH_COMMANDS.map((c) => (
                  <div key={c.name} className="contents">
                    <dt className="font-mono text-ember">{c.name}</dt>
                    <dd className="text-ash">{c.hint}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {error && <p className="text-[13px] text-bile">{error}</p>}
          {!text && !error && [0, 1, 2].map((i) => <div key={i} className="shimmer h-24 rounded-2xl" />)}
          {text && shown.length === 0 && (
            <p className="py-6 text-center text-[13px] text-ash">No command matches â€œ{query}â€.</p>
          )}

          {shown.map((s, idx) => (
            <article
              key={s.title}
              className="help-section-card tile rounded-2xl border border-scar/40 bg-abyss/85 p-5 shadow-lg transition hover:border-scar/80"
            >
              <div className="flex items-center justify-between gap-3 border-b border-scar/30 pb-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-scar/50 text-[11px] font-mono font-bold text-ember">
                    {idx + 1}
                  </span>
                  <h3 className="text-[14.5px] font-semibold text-bone truncate">{s.title}</h3>
                </div>
                {s.commands.length > 0 && (
                  <span className="shrink-0 rounded-full bg-scar/30 px-2 py-0.5 text-[10.5px] font-medium text-ash">
                    {s.commands.length} {s.commands.length === 1 ? 'command' : 'commands'}
                  </span>
                )}
              </div>

              {s.purpose ? (
                <div className="mt-3.5 space-y-3">
                  <div className="rounded-xl border border-scar/40 bg-scar/20 p-3 text-[12.5px] leading-relaxed text-bone/90">
                    <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-ember">
                      Purpose
                    </span>
                    {s.purpose}
                  </div>

                  {s.commands.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="block text-[10.5px] font-semibold uppercase tracking-wider text-smoke">
                        Voice & Text Commands (Click to run)
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {s.commands.map((cmd, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => onRun(cmd)}
                            className="group flex items-center gap-1.5 rounded-lg border border-scar/60 bg-abyss/90 px-3 py-1.5 text-[12px] font-mono text-bone transition hover:border-ember hover:bg-crimson/30 hover:text-white hover:shadow-md"
                            title={`Run: "${cmd}"`}
                          >
                            <span className="text-ember transition group-hover:scale-125">â–¶</span>
                            <span>"{cmd}"</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {s.notes && (
                    <div className="rounded-lg border border-scar/20 bg-abyss/40 px-3 py-2 text-[11.5px] text-ash">
                      <Body text={s.notes} onRun={onRun} />
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-3">
                  <Body text={s.body} onRun={onRun} />
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
