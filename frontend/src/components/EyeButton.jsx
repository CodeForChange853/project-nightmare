import Orb from './Orb'

/**
 * The blood-moon eye as a hold-to-talk button. Shared by the graph, the mini window and the phone.
 * Evolves its outer socket and orbital HUD reticles across Level 1, Level 3, and Level 5.
 */
export default function EyeButton({
  mode,
  canTalk,
  onPressStart,
  onPressEnd,
  style,
  className = '',
  clearanceLevel = 1,
}) {
  const isL5 = clearanceLevel === 5
  const isL3 = clearanceLevel === 3

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
      className={`group relative touch-none select-none rounded-full transition-shadow duration-700 disabled:cursor-default ${className} ${
        isL5
          ? 'shadow-[0_0_65px_-8px_rgba(255,209,102,0.42),0_0_110px_-15px_rgba(220,20,60,0.58)]'
          : isL3
            ? 'shadow-[0_0_45px_-8px_rgba(232,163,61,0.34),0_0_80px_-18px_rgba(220,20,60,0.45)]'
            : ''
      }`}
    >
      {/* Socket radial depth */}
      <span
        className={`absolute inset-[6%] rounded-full transition-all duration-700 ${
          isL5
            ? 'bg-[radial-gradient(circle,rgba(65,12,20,0.92)_0%,rgba(19,7,10,0.72)_58%,transparent_74%)] shadow-[inset_0_0_85px_rgba(255,209,102,0.18)]'
            : isL3
              ? 'bg-[radial-gradient(circle,rgba(52,14,12,0.88)_0%,rgba(19,7,10,0.65)_56%,transparent_72%)] shadow-[inset_0_0_80px_rgba(232,163,61,0.15)]'
              : 'bg-[radial-gradient(circle,rgba(40,6,12,0.85)_0%,rgba(19,7,10,0.6)_55%,transparent_72%)] shadow-[inset_0_0_80px_rgba(220,20,60,0.12)]'
        }`}
      />

      {/* Primary socket rim */}
      <span
        className={`absolute inset-[6%] rounded-full border transition-all duration-700 ${
          isL5
            ? 'border-[#ffd166]/65 shadow-[inset_0_0_32px_rgba(255,209,102,0.22)]'
            : isL3
              ? 'border-bile/55 shadow-[inset_0_0_22px_rgba(232,163,61,0.16)]'
              : 'border-scar/40'
        }`}
      />

      {/* L3 & L5 Tactical Orbital SVG Reticle */}
      {(isL3 || isL5) && (
        <svg
          aria-hidden
          viewBox="0 0 200 200"
          className="pointer-events-none absolute inset-[1%] h-[98%] w-[98%] overflow-visible"
        >
          {/* Outer segmented telemetry arc */}
          <circle
            cx="100"
            cy="100"
            r="93"
            fill="none"
            stroke={isL5 ? '#ffd166' : '#e8a33d'}
            strokeOpacity={isL5 ? '0.55' : '0.4'}
            strokeWidth={isL5 ? '1.1' : '0.9'}
            strokeDasharray={isL5 ? '18 8 4 8' : '28 16'}
            className=" origin-center orbit-slow"
          />
          {/* Cardinal bracket ticks */}
          {[0, 90, 180, 270].map((deg) => (
            <g key={deg} transform={`rotate(${deg} 100 100)`}>
              <line
                x1="100"
                y1="2"
                x2="100"
                y2={isL5 ? '9' : '7'}
                stroke={isL5 ? '#ffd166' : '#e8a33d'}
                strokeWidth={isL5 ? '1.6' : '1.2'}
                strokeOpacity={isL5 ? '0.85' : '0.65'}
              />
            </g>
          ))}
          {/* L5 Architect diagonal eclipse ticks & inner counter-ring */}
          {isL5 && (
            <>
              {[45, 135, 225, 315].map((deg) => (
                <g key={deg} transform={`rotate(${deg} 100 100)`}>
                  <circle cx="100" cy="6.5" r="1.6" fill="#ff5466" fillOpacity="0.9" />
                </g>
              ))}
              <circle
                cx="100"
                cy="100"
                r="88"
                fill="none"
                stroke="#ff5466"
                strokeOpacity="0.4"
                strokeWidth="0.8"
                strokeDasharray="6 14"
                className="origin-center orbit-reverse"
              />
            </>
          )}
        </svg>
      )}

      <Orb mode={mode} clearanceLevel={clearanceLevel} className="relative" />
    </button>
  )
}
