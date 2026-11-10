import Orb from './Orb'

/**
 * The Crimson Cosmic Eye Sigil as a hold-to-talk interactive talisman.
 * Shared by the main NodeGraph, Level 5 Command Center, MiniView, and PhoneView.
 * Features a volumetric Fog Light bloom when holding Space or the Mic button (`mode === 'listening'`),
 * and a calm breathing astral idle state.
 */
export default function EyeButton({
  mode,
  canTalk,
  onPressStart,
  onPressEnd,
  style,
  className = '',
}) {
  const isListening = mode === 'listening'
  const isSpeaking = mode === 'speaking'
  const isIdle = mode === 'idle'

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
      title={canTalk ? 'Hold to talk (or hold Space)' : undefined}
      style={style}
      className={`group relative touch-none select-none rounded-full transition-all duration-500 disabled:cursor-default ${className} ${
        isListening
          ? 'shadow-[0_0_95px_12px_rgba(255,30,66,0.75),0_0_160px_28px_rgba(255,209,102,0.45)] scale-[1.03]'
          : 'shadow-[0_0_70px_-6px_rgba(255,209,102,0.42),0_0_120px_-12px_rgba(220,20,60,0.62)]'
      }`}
    >
      {/* VOLUMETRIC FOG LIGHT BLOOM (Ignites when holding Space or Mic button) */}
      <span
        aria-hidden
        className={`pointer-events-none absolute -inset-[28%] rounded-full transition-all duration-500 ${
          isListening
            ? 'opacity-100 scale-110 animate-pulse'
            : isSpeaking
              ? 'opacity-65 scale-100'
              : isIdle
                ? 'opacity-30 scale-95'
                : 'opacity-20 scale-90'
        }`}
        style={{
          background: isListening
            ? 'radial-gradient(circle, rgba(255,225,130,0.38) 0%, rgba(255,30,66,0.48) 32%, rgba(165,8,34,0.28) 58%, transparent 76%)'
            : 'radial-gradient(circle, rgba(255,190,90,0.16) 0%, rgba(220,20,60,0.24) 42%, transparent 72%)',
          filter: isListening ? 'blur(18px)' : 'blur(12px)',
        }}
      />

      {/* Secondary Swirling Fog-Light Conic Plume on Space / Mic Hold */}
      <span
        aria-hidden
        className={`pointer-events-none absolute -inset-[18%] rounded-full orbit-slow transition-opacity duration-500 ${
          isListening ? 'opacity-95' : 'opacity-0'
        }`}
        style={{
          background:
            'conic-gradient(from 0deg, transparent 0deg, rgba(255,38,75,0.42) 45deg, rgba(255,209,102,0.45) 90deg, transparent 135deg, rgba(255,38,75,0.38) 215deg, rgba(255,209,102,0.42) 270deg, transparent 360deg)',
          filter: 'blur(22px)',
        }}
      />

      {/* Deep Cosmic Socket Radial Depth */}
      <span
        className={`absolute inset-[8%] rounded-full transition-all duration-700 ${
          isListening
            ? 'bg-[radial-gradient(circle,rgba(95,14,28,0.95)_0%,rgba(28,4,9,0.82)_58%,transparent_76%)] shadow-[inset_0_0_95px_rgba(255,209,102,0.35)]'
            : 'bg-[radial-gradient(circle,rgba(65,10,18,0.92)_0%,rgba(16,4,7,0.75)_58%,transparent_75%)] shadow-[inset_0_0_85px_rgba(255,209,102,0.2)]'
        }`}
      />

      {/* Crimson Cosmic Eye Sigil Outer SVG Filigree & Orbital Nodes */}
      <svg
        aria-hidden
        viewBox="0 0 200 200"
        className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
      >
        {/* Outer segmented astrolabe ring */}
        <circle
          cx="100"
          cy="100"
          r="86"
          fill="none"
          stroke={isListening ? '#fff3b0' : '#ffd166'}
          strokeOpacity={isListening ? '0.88' : '0.6'}
          strokeWidth={isListening ? '1.5' : '1.1'}
          strokeDasharray="16 6 3 6"
          className="origin-center orbit-slow"
        />

        {/* Counter-rotating inner sigil track */}
        <circle
          cx="100"
          cy="100"
          r="78"
          fill="none"
          stroke="#ff2a4b"
          strokeOpacity={isListening ? '0.8' : '0.45'}
          strokeWidth="0.9"
          strokeDasharray="5 11"
          className="origin-center orbit-reverse"
        />

        {/* Diagonal cosmic star nodes */}
        {[45, 135, 225, 315].map((deg) => (
          <g key={deg} transform={`rotate(${deg} 100 100)`}>
            <circle
              cx="100"
              cy="14"
              r={isListening ? '2' : '1.4'}
              fill="#ffd166"
              fillOpacity={isListening ? '0.95' : '0.7'}
            />
          </g>
        ))}
      </svg>

      <Orb mode={mode} className="relative z-10" />
    </button>
  )
}
