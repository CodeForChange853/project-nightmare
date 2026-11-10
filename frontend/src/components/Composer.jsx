import { useState } from 'react'
import { SLASH_COMMANDS } from '../slashCommands'
import Icon from './Icon'

/**
 * Text input plus the voice controls (mic, language, male/female voice, reading speed, mute), docked at the bottom.
 * `compact` (mini window) keeps only the mic, mute and Stop.
 */
export default function Composer({
  disabled,
  onSubmit,
  listening,
  micSupported,
  canTalk,
  onPressStart,
  onPressEnd,
  lang,
  onToggleLang,
  muted,
  onToggleMute,
  voiceGender,
  onToggleVoiceGender,
  rate,
  onCycleRate,
  speaking,
  onStopSpeaking,
  speechError,
  compact = false,
}) {
  const [draft, setDraft] = useState('')
  const [pick, setPick] = useState(0)
  const [dismissed, setDismissed] = useState(false)

  // slash suggestions while the first word starts with "/"
  const typed = draft.trimStart()
  const suggestions =
    typed.startsWith('/') && !/\s/.test(typed) && !dismissed
      ? SLASH_COMMANDS.filter((c) => c.name.startsWith(typed.toLowerCase()))
      : []
  const send = (text) => {
    setDraft('')
    setPick(0)
    onSubmit(text)
  }

  const onKeyDown = (e) => {
    if (!suggestions.length) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      setPick((p) => (p + step + suggestions.length) % suggestions.length)
    } else if (e.key === 'Tab') {
      e.preventDefault()
      setDraft(suggestions[Math.min(pick, suggestions.length - 1)].name)
    } else if (e.key === 'Enter') {
      const exact = suggestions.find((c) => c.name === typed.toLowerCase())
      e.preventDefault()
      send((exact ?? suggestions[Math.min(pick, suggestions.length - 1)]).name)
    } else if (e.key === 'Escape') {
      e.stopPropagation()
      setDismissed(true)
    }
  }

  return (
    <div className="border-t border-scar/40 p-3">
      <div className="relative">
        {suggestions.length > 0 && (
          <ul
            id="slash-list"
            role="listbox"
            aria-label="Commands"
            className="glass absolute inset-x-0 bottom-full mb-2 overflow-hidden rounded-2xl p-1.5"
          >
            {suggestions.map((c, i) => (
              <li key={c.name} role="option" aria-selected={i === pick}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()} // keep focus in the input
                  onMouseEnter={() => setPick(i)}
                  onClick={() => send(c.name)}
                  className={`flex w-full items-baseline gap-3 rounded-xl px-3 py-2 text-left ${
                    i === pick ? 'bg-scar/55' : ''
                  }`}
                >
                  <span className="font-mono text-[13px] text-ember">{c.name}</span>
                  <span className="truncate text-[12px] text-ash">{c.hint}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            send(draft)
          }}
          className="flex items-center gap-2 rounded-2xl border border-[#ffd166]/55 bg-abyss/75 py-1.5 pl-3 pr-1.5 transition-all focus-within:border-[#ffd166] focus-within:shadow-[0_0_0_4px_rgba(255,209,102,0.18)]"
        >
          {/* Level 5 Architect Tag on input */}
          <span
            className="hidden shrink-0 items-center gap-1 rounded-lg border border-[#ffd166]/40 bg-[#ffd166]/20 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-[#ffd166] sm:flex"
          >
            L5 // ARCHITECT
          </span>

          <input
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              setPick(0)
              setDismissed(false)
            }}
            onKeyDown={onKeyDown}
            disabled={disabled}
            placeholder={
              compact
                ? 'L5 Shell / Ask Nightmare…'
                : 'Architect Console: raw shell command or chat, / for commands'
            }
            aria-label="Command"
            aria-controls={suggestions.length ? 'slash-list' : undefined}
            aria-expanded={suggestions.length > 0}
            autoComplete="off"
            spellCheck={false}
            className="min-w-0 flex-1 bg-transparent text-[14px] text-bone outline-none placeholder:text-smoke focus-visible:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || !draft.trim()}
            aria-label="Send"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-b from-[#ffd166] via-amber-400 to-crimson font-bold text-black shadow-[0_6px_20px_-4px_rgba(255,209,102,0.6)] transition-all hover:brightness-110 disabled:opacity-35"
          >
            <Icon name="send" size={16} />
          </button>
        </form>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={!canTalk}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId)
            onPressStart()
          }}
          onPointerUp={onPressEnd}
          onPointerCancel={onPressEnd}
          onContextMenu={(e) => e.preventDefault()}
          className={`flex touch-none select-none items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[12px] disabled:opacity-40 ${
            listening
              ? 'border-ember bg-crimson/25 text-white shadow-[0_0_22px_-4px_rgba(255,84,102,0.8)]'
              : 'border-scar/70 text-ash hover:text-bone'
          }`}
        >
          <Icon name="mic" size={14} className={listening ? 'text-ember' : ''} />
          {listening ? 'Release to send' : 'Hold to talk'}
        </button>
        {micSupported && !compact && (
          <button
            type="button"
            onClick={onToggleLang}
            title="Speech recognition language"
            className="flex items-center gap-1.5 rounded-xl border border-scar/70 px-2.5 py-1.5 text-[12px] text-ash hover:text-bone"
          >
            <Icon name="globe" size={14} />
            {lang}
          </button>
        )}
        <button
          type="button"
          onClick={onToggleMute}
          aria-pressed={!muted}
          title={muted ? 'Spoken replies are off' : 'Spoken replies are on'}
          className="flex items-center gap-1.5 rounded-xl border border-scar/70 px-2.5 py-1.5 text-[12px] text-ash hover:text-bone"
        >
          <Icon name={muted ? 'mute' : 'voice'} size={14} />
          {muted ? 'Voice off' : 'Voice on'}
        </button>
        {onToggleVoiceGender && !compact && (
          <button
            type="button"
            onClick={onToggleVoiceGender}
            title="Switch AI voice between Male and Female"
            className="rounded-xl border border-scar/70 px-2.5 py-1.5 text-[12px] capitalize text-ash hover:text-bone"
          >
            {voiceGender}
          </button>
        )}
        {onCycleRate && !compact && (
          <button
            type="button"
            onClick={onCycleRate}
            title="Cycle AI reading speed (0.9x, 1x, 1.15x, 1.3x, 1.5x)"
            className="rounded-xl border border-scar/70 px-2.5 py-1.5 text-[12px] text-ash hover:text-bone"
          >
            {rate}x
          </button>
        )}
        {speaking && onStopSpeaking && (
          <button
            type="button"
            onClick={onStopSpeaking}
            title="Stop reading aloud"
            className="rounded-xl border border-ember/60 bg-crimson/20 px-2.5 py-1.5 text-[12px] text-ember hover:text-bone"
          >
            Stop
          </button>
        )}
      </div>
      {speechError && <p className="mt-2 text-[12px] text-ember">Speech error: {speechError}</p>}
    </div>
  )
}
