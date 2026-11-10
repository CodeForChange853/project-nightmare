import AnswerCard from './AnswerCard'
import Composer from './Composer'
import EyeButton from './EyeButton'
import Icon, { Sigil } from './Icon'

/**
 * The compact window the Ctrl+Alt+N helper opens: the eye, the latest answer and a text box.
 * Hold Space (the window has focus) or the eye to talk; "home" or the expand button asks for the full view.
 */
export default function MiniView({
  status,
  offline,
  mode,
  title,
  caption,
  canTalk,
  onPressStart,
  onPressEnd,
  answer,
  asked,
  busy,
  elapsed,
  speaking,
  onSpeak,
  onStop,
  onHome,
  composer,
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 px-3 pt-2.5">
        <Sigil
          size={22}
          className="shrink-0 drop-shadow-[0_0_10px_rgba(220,20,60,0.5)] transition-all duration-700"
        />
        <p className="font-display text-[14px] font-extrabold uppercase tracking-[0.2em] text-bone">Nightmare</p>
        <span
          className={`ml-1 h-2 w-2 rounded-full ${offline ? 'bg-smoke' : 'pulse-dot bg-crimson'}`}
          title={offline ? 'Backend offline' : 'Online'}
        />
        {status?.role === 'readonly' && <span className="text-[11px] text-bile">Read-only</span>}
        <span
          className="ml-auto rounded-full border border-[#ffd166]/80 bg-[#ffd166]/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#ffd166] shadow-[0_0_10px_rgba(255,209,102,0.35)]"
          title="Level 5 Architect Authority"
        >
          L5 ARCHITECT
        </span>
        <button
          type="button"
          onClick={onHome}
          title="Full view (or say “home”)"
          aria-label="Full view"
          className="ml-1.5 grid h-7 w-7 place-items-center rounded-full border border-scar/60 text-ash hover:text-bone"
        >
          <Icon name="expand" size={14} />
        </button>
      </header>

      <div className="flex flex-col items-center gap-1 pt-1">
        <EyeButton
          mode={mode}
          canTalk={canTalk}
          onPressStart={onPressStart}
          onPressEnd={onPressEnd}
          style={{ width: 'min(40vw, 150px)', aspectRatio: '1' }}
        />
        <p className="font-display text-[17px] font-bold uppercase leading-none tracking-[0.16em] text-bone">{title}</p>
        <p className="max-w-[34ch] truncate px-3 text-center text-[12px] text-ash" aria-live="polite">
          {caption}
          {mode === 'listening' && <span className="caret ml-0.5 text-ember">▌</span>}
        </p>
      </div>

      <AnswerCard
        className="mx-3 mt-3 flex-1"
        entry={answer}
        asked={asked}
        busy={busy}
        elapsed={elapsed}
        speaking={speaking}
        onSpeak={onSpeak}
        onStop={onStop}
        empty="Hold Space and speak, or type below. Say “home” for the full view."
      />

      <Composer {...composer} compact />
    </div>
  )
}
