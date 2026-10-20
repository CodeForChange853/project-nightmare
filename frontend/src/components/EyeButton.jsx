import Orb from './Orb'

/** The blood-moon eye as a hold-to-talk button. Shared by the graph, the mini window and the phone. */
export default function EyeButton({ mode, canTalk, onPressStart, onPressEnd, style, className = '' }) {
  return (
    <button
      type="button"
      data-orb
      disabled={!canTalk}
      onPointerDown={(e) => {
        if (!canTalk) return
        e.currentTarget.setPointerCapture(e.pointerId)
        onPressStart()
      }}
      onPointerUp={onPressEnd}
      onPointerCancel={onPressEnd}
      onContextMenu={(e) => e.preventDefault()}
      aria-label="Hold to talk"
      title={canTalk ? 'Hold to talk' : undefined}
      style={style}
      className={`relative touch-none select-none rounded-full disabled:cursor-default ${className}`}
    >
      <span className="absolute inset-[6%] rounded-full bg-[radial-gradient(circle,rgba(40,6,12,0.85)_0%,rgba(19,7,10,0.6)_55%,transparent_72%)] shadow-[inset_0_0_80px_rgba(220,20,60,0.12)]" />
      <span className="absolute inset-[6%] rounded-full border border-scar/40" />
      <Orb mode={mode} className="relative" />
    </button>
  )
}
