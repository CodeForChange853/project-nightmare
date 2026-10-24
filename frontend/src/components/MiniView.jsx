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
  onOpenClearance,
}) {
  const clearanceLevel = status?.clearance_level ?? 1
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 px-3 pt-2.5">
        <Sigil
          size={22}
          clearanceLevel={clearanceLevel}
          className="shrink-0 drop-shadow-[0_0_10px_rgba(220,20,60,0.5)] transition-all duration-700"
        />
        <p className="font-display text-[14px] font-extrabold uppercase tracking-[0.2em] text-bone">Nightmare</p>
        <span
          className={`ml-1 h-2 w-2 rounded-full ${offline ? 'bg-smoke' : 'pulse-dot bg-crimson'}`}
          title={offline ? 'Backend offline' : 'Online'}
        />
        {status?.role === 'readonly' && <span className="text-[11px] text-bile">Read-only</span>}
        <button
          type="button"
          onClick={onOpenClearance}
          className={`ml-auto rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider transition-all ${
            clearanceLevel === 5
              ? 'border border-[#ffd166]/80 bg-[#ffd166]/20 text-[#ffd166] shadow-[0_0_10px_rgba(255,209,102,0.35)]'
              : clearanceLevel === 3
                ? 'border border-amber-400/70 bg-amber-500/20 text-amber-300 shadow-[0_0_8px_rgba(232,163,61,0.25)]'
                : 'border border-scar/40 bg-scar/10 text-smoke hover:text-bone hover:border-scar/70'
          }`}
          title={status?.clearance_label || 'Clearance. Click to switch.'}
        >
          {clearanceLevel === 5 ? 'L5 ARCHITECT' : clearanceLevel === 3 ? 'L3 OPERATOR' : 'L1 OBSERVER'}
        </button>
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
          clearanceLevel={clearanceLevel}
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
