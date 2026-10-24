import Icon, { Sigil } from './Icon'

/** The latest answer right under the eye (mini window, phone Talk tab), with Read aloud / Stop. */
export default function AnswerCard({ entry, asked, busy, elapsed, speaking, onSpeak, onStop, empty, onMore, className = '' }) {
  return (
    <section
      aria-label="Latest answer"
      aria-live="polite"
      className={`flex min-h-0 flex-col rounded-2xl border border-scar/50 bg-abyss/50 p-3.5 ${className}`}
    >
      {asked && (
        <p className="mb-2 truncate text-[12px] text-smoke">
          You: <span className="text-ash">{asked}</span>
        </p>
      )}
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {busy ? (
          <p className="flex items-center gap-2 text-[13px] text-ash">
            <span className="pulse-dot h-2 w-2 rounded-full bg-crimson" />
            Thinking for {elapsed}s
          </p>
        ) : entry ? (
          <div className="flex gap-2.5">
            {entry.role === 'system' ? (
              <Icon name="warn" size={16} className="mt-0.5 shrink-0 text-bile" />
            ) : (
              <Sigil size={20} className="mt-0.5 shrink-0" />
            )}
            <p
              className={`whitespace-pre-wrap break-words text-[14px] leading-relaxed ${
                entry.role === 'system' || entry.ok === false ? 'text-bile' : 'text-bone'
              }`}
            >
              {entry.text}
            </p>
          </div>
        ) : (
          <p className="text-[13px] leading-relaxed text-ash">{empty}</p>
        )}
      </div>
      {(entry || onMore) && !busy && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {entry?.role === 'nightmare' &&
            (speaking ? (
              <button
                type="button"
                onClick={onStop}
                className="flex min-h-9 items-center gap-1.5 rounded-xl border border-ember/60 bg-crimson/20 px-3 text-[12px] text-ember"
              >
                <Icon name="mute" size={13} /> Stop
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onSpeak(entry.text)}
                className="flex min-h-9 items-center gap-1.5 rounded-xl border border-scar/60 px-3 text-[12px] text-ash hover:text-bone"
              >
                <Icon name="voice" size={13} /> Read aloud
              </button>
            ))}
          {onMore && (
            <button
              type="button"
              onClick={onMore}
              className="ml-auto flex min-h-9 items-center gap-1 rounded-xl px-2 text-[12px] text-ash hover:text-bone"
            >
              Conversation <Icon name="chevron" size={13} />
            </button>
          )}
        </div>
      )}
    </section>
  )
}
