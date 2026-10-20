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
// an unindented line with no lowercase letters, like "HOW TO SPEAK TO NIGHTMARE" (digits like "8b." aside)
const isCaps = (l) =>
  l.trim() && l === l.trimStart() && !l.startsWith('-') && /[A-Z]{3}/.test(l) && l.replace(/^\d+[a-z]?\./, '') === l.replace(/^\d+[a-z]?\./, '').toUpperCase()

/** Split nightmare_helper.txt into titled sections: a line framed by ---- rules, or an ALL-CAPS line. */
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
  return sections.map((s) => ({ title: s.title, body: s.lines.join('\n').trim() })).filter((s) => s.body)
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
              className="rounded-md bg-scar/40 px-1.5 text-bone underline decoration-crimson/60 underline-offset-2 hover:bg-crimson/30"
            >
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
      .from(root.current, { opacity: 0, duration: 0.2 })
      .from(card.current, { y: 24, opacity: 0, duration: 0.45, ease: 'expo.out' }, 0.05)
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
        className="glass flex max-h-[88dvh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl"
      >
        <header className="flex items-center gap-3 border-b border-scar/40 px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-scar/60 text-ember">
            <Icon name="spark" size={17} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="help-title" className="text-[16px] font-semibold text-bone">
              Commands
            </h2>
            <p className="text-[12px] text-smoke">Say these, or type them. Click a highlighted command to run it.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close commands"
            className="grid h-8 w-8 place-items-center rounded-full border border-scar/60 text-ash hover:text-bone"
          >
            <Icon name="close" size={15} />
          </button>
        </header>

        <div className="border-b border-scar/40 px-5 py-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search commands, like reminder or youtube"
            aria-label="Search commands"
            autoFocus
            className="w-full rounded-xl border border-scar/60 bg-abyss/70 px-3.5 py-2 text-[13px] text-bone outline-none placeholder:text-smoke focus:border-ember/70"
          />
        </div>

        <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto p-5">
          {!q && (
            <div className="tile rounded-2xl p-4">
              <h3 className="text-[14px] font-medium text-bone">Typed shortcuts</h3>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[12.5px]">
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
          {!text && !error &&
            [0, 1, 2].map((i) => <div key={i} className="shimmer h-24 rounded-2xl" />)}
          {text && shown.length === 0 && (
            <p className="py-6 text-center text-[13px] text-ash">No command mentions “{query}”.</p>
          )}
          {shown.map((s) => (
            <article key={s.title} className="tile rounded-2xl p-4">
              <h3 className="text-[14px] font-medium text-bone">{s.title}</h3>
              <div className="mt-2">
                <Body text={s.body} onRun={onRun} />
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
