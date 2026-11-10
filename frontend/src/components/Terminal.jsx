import { useEffect, useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'
import Icon, { Sigil } from './Icon'

function Entry({ entry, onSpeak }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tween =
      entry.role === 'nightmare'
        ? gsap.fromTo(
            ref.current,
            { clipPath: 'inset(0 0 100% 0)', y: 8, opacity: 0 },
            { clipPath: 'inset(0 0 0% 0)', y: 0, opacity: 1, duration: 0.7, ease: 'power3.out', clearProps: 'clipPath' },
          )
        : gsap.fromTo(ref.current, { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: 'power2.out' })
    return () => tween.kill()
  }, [entry.role])

  if (entry.role === 'you') {
    return (
      <div ref={ref} className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md border border-scar/50 bg-scar/30 px-3.5 py-2 text-[13px] text-bone">
          {entry.text}
        </p>
      </div>
    )
  }

  if (entry.role === 'system') {
    return (
      <div ref={ref} className="flex gap-2 rounded-xl border border-bile/30 bg-bile/5 px-3 py-2 text-[12px] text-bile">
        <Icon name="warn" size={15} className="mt-px shrink-0" />
        <p className="whitespace-pre-wrap break-words">{entry.text}</p>
      </div>
    )
  }

  const bad = entry.ok === false
  return (
    <div ref={ref} className="flex gap-3">
      <Sigil size={22} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-smoke">
          {entry.understood ? (
            <span>
              Understood as <span className="text-ash">{entry.understood.replaceAll('_', ' ')}</span>
            </span>
          ) : (
            <span />
          )}
          {onSpeak && (
            <button
              type="button"
              onClick={() => onSpeak(entry.text)}
              title="Read this reply aloud"
              className="flex items-center gap-1 rounded-md border border-scar/60 px-2 py-0.5 text-[10px] text-ash hover:border-ember/60 hover:text-bone"
            >
              <Icon name="voice" size={11} /> Read aloud
            </button>
          )}
        </div>
        <p
          className={`whitespace-pre-wrap break-words border-l-2 pl-3 text-[13.5px] leading-relaxed ${
            bad ? 'border-bile/60 text-bile' : 'border-crimson/70 text-bone'
          }`}
        >
          {entry.text}
        </p>
        {entry.link && (
          <a
            href={entry.link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-3 mt-2 inline-flex max-w-full items-center gap-1.5 rounded-lg border border-scar/60 px-2.5 py-1 text-[12px] text-ash hover:border-ember/60 hover:text-bone"
          >
            <Icon name="external" size={13} className="shrink-0 text-ember" />
            <span className="truncate">
              {entry.link.label || (entry.link.blocked ? 'Your browser blocked the new tab. Open it here' : 'Open again')}
            </span>
          </a>
        )}
      </div>
    </div>
  )
}

function Thinking({ elapsed }) {
  return (
    <div className="flex gap-3" aria-live="polite">
      <Sigil size={22} className="mt-0.5 shrink-0 animate-pulse" />
      <div className="min-w-0 flex-1 space-y-2 border-l-2 border-scar/60 pl-3">
        <p className="text-[12px] text-ash">Thinking for {elapsed}s</p>
        <div className="shimmer h-2.5 w-[88%] rounded-full" />
        <div className="shimmer h-2.5 w-[64%] rounded-full" />
        <div className="shimmer h-2.5 w-[40%] rounded-full" />
      </div>
    </div>
  )
}

export default function Terminal({ entries, busy, elapsed, onSpeak }) {
  const box = useRef(null)

  useEffect(() => {
    const el = box.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [entries, busy])

  return (
    <div ref={box} className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4" role="log" aria-label="Conversation">
      {entries.length === 0 && !busy && (
        <div className="grid h-full place-items-center text-center">
          <div>
            <p className="text-[15px] text-bone">Nothing said yet</p>
            <p className="mx-auto mt-1.5 max-w-[30ch] text-[13px] leading-relaxed text-ash">
              {window.matchMedia('(pointer: coarse)').matches ? (
                'Hold the eye and speak, or type below.'
              ) : (
                <>
                  Hold <kbd className="rounded border border-scar px-1 font-mono text-[11px] text-bone">Space</kbd> and speak, or
                  type below.
                </>
              )}{' '}
              Try â€œprogress of bimsâ€.
            </p>
          </div>
        </div>
      )}
      {entries.map((entry) => (
        <Entry key={entry.id} entry={entry} onSpeak={onSpeak} />
      ))}
      {busy && <Thinking elapsed={elapsed} />}
    </div>
  )
}
