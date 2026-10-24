import { useEffect, useRef } from 'react'
import gsap from 'gsap'

/**
 * Ambient space behind Nightmare: slow pools of light over a dot grid, vignette, film grain,
 * and a tactical viewport perimeter frame that intensifies at Clearance Level 3 and Level 5.
 */
export default function Background({ clearanceLevel = 1 }) {
  const left = useRef(null)
  const right = useRef(null)
  const corona = useRef(null)
  const frameRef = useRef(null)

  const isL5 = clearanceLevel === 5
  const isL3 = clearanceLevel === 3

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tweens = [
      gsap.to(left.current, {
        xPercent: 6,
        yPercent: -5,
        opacity: 0.78,
        duration: 9,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
      }),
      gsap.to(right.current, {
        xPercent: -5,
        yPercent: 7,
        opacity: 0.55,
        duration: 12,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
      }),
    ]
    return () => tweens.forEach((t) => t.kill())
  }, [])

  // Animate the perimeter HUD frame when clearance changes
  useEffect(() => {
    if (!frameRef.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    if (clearanceLevel > 1) {
      gsap.fromTo(
        frameRef.current,
        { opacity: 0, scale: 1.015 },
        { opacity: 1, scale: 1, duration: 0.75, ease: 'expo.out' },
      )
    }
  }, [clearanceLevel])

  const leftGrad = isL5
    ? 'radial-gradient(closest-side, rgba(255,30,66,0.24), rgba(232,163,61,0.08), transparent)'
    : isL3
      ? 'radial-gradient(closest-side, rgba(232,120,45,0.20), rgba(220,20,60,0.08), transparent)'
      : 'radial-gradient(closest-side, rgba(220,20,60,0.16), transparent)'

  const rightGrad = isL5
    ? 'radial-gradient(closest-side, rgba(255,209,102,0.20), rgba(180,12,40,0.14), transparent)'
    : isL3
      ? 'radial-gradient(closest-side, rgba(232,163,61,0.18), rgba(150,10,35,0.12), transparent)'
      : 'radial-gradient(closest-side, rgba(150,10,35,0.22), transparent)'

  const dotColor = isL5
    ? 'rgba(255,209,102,0.24)'
    : isL3
      ? 'rgba(232,163,61,0.20)'
      : 'rgba(255,84,102,0.16)'

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-abyss">
      <div
        ref={left}
        className="absolute -left-[15%] top-[10%] h-[80vh] w-[70vw] opacity-100 transition-[background] duration-1000"
        style={{ background: leftGrad }}
      />
      <div
        ref={right}
        className="absolute -right-[10%] -top-[20%] h-[70vh] w-[50vw] opacity-80 transition-[background] duration-1000"
        style={{ background: rightGrad }}
      />
      <div
        ref={corona}
        className={`absolute left-1/2 top-0 h-[45vh] w-[80vw] -translate-x-1/2 transition-opacity duration-1000 ${
          isL5 ? 'opacity-90' : isL3 ? 'opacity-45' : 'opacity-0'
        }`}
        style={{
          background: isL5
            ? 'radial-gradient(ellipse at 50% 0%, rgba(255,209,102,0.15), rgba(220,20,60,0.08) 55%, transparent 80%)'
            : 'radial-gradient(ellipse at 50% 0%, rgba(232,163,61,0.10), transparent 70%)',
        }}
      />
      <div
        className="absolute inset-0 opacity-55 transition-all duration-1000"
        style={{
          backgroundImage: `radial-gradient(${dotColor} 1px, transparent 1.2px)`,
          backgroundSize: isL5 ? '24px 24px' : '26px 26px',
          maskImage: 'radial-gradient(ellipse 74% 64% at 35% 50%, #000 12%, transparent 78%)',
          WebkitMaskImage: 'radial-gradient(ellipse 74% 64% at 35% 50%, #000 12%, transparent 78%)',
        }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.78)_100%)]" />

      {/* Tactical Viewport Perimeter HUD for L3 (Operator) and L5 (Architect) */}
      {(isL3 || isL5) && (
        <div ref={frameRef} className="absolute inset-0">
          {/* Top laser hairline */}
          <div
            className={`absolute inset-x-0 top-0 h-[1.5px] ${
              isL5
                ? 'bg-gradient-to-r from-transparent via-[#ffd166]/80 to-transparent shadow-[0_0_16px_rgba(255,209,102,0.65)]'
                : 'bg-gradient-to-r from-transparent via-bile/55 to-transparent shadow-[0_0_10px_rgba(232,163,61,0.35)]'
            }`}
          />
          {/* Bottom laser hairline */}
          <div
            className={`absolute inset-x-0 bottom-0 h-[1px] ${
              isL5
                ? 'bg-gradient-to-r from-transparent via-ember/65 to-transparent'
                : 'bg-gradient-to-r from-transparent via-bile/35 to-transparent'
            }`}
          />

          {/* 4 Corner HUD Brackets */}
          <span
            className={`absolute left-2.5 top-2.5 h-5 w-5 border-l-2 border-t-2 rounded-tl-sm ${
              isL5 ? 'border-[#ffd166]/70' : 'border-bile/45'
            }`}
          />
          <span
            className={`absolute right-2.5 top-2.5 h-5 w-5 border-r-2 border-t-2 rounded-tr-sm ${
              isL5 ? 'border-[#ffd166]/70' : 'border-bile/45'
            }`}
          />
          <span
            className={`absolute bottom-2.5 left-2.5 h-5 w-5 border-b-2 border-l-2 rounded-bl-sm ${
              isL5 ? 'border-[#ffd166]/70' : 'border-bile/45'
            }`}
          />
          <span
            className={`absolute bottom-2.5 right-2.5 h-5 w-5 border-b-2 border-r-2 rounded-br-sm ${
              isL5 ? 'border-[#ffd166]/70' : 'border-bile/45'
            }`}
          />

          {/* Subtle corner telemetry watermarks on desktop */}
          <div className="hidden lg:flex absolute bottom-3 left-6 items-center gap-2 font-mono text-[9px] tracking-[0.22em] uppercase text-smoke/55">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isL5 ? 'bg-[#ffd166] shadow-[0_0_6px_#ffd166]' : 'bg-bile'
              }`}
            />
            {isL5
              ? 'SYS.CLEARANCE // LVL.05 ARCHITECT · SHELL UNRESTRICTED'
              : 'SYS.CLEARANCE // LVL.03 OPERATOR · MUTATIONS ACTIVE'}
          </div>
        </div>
      )}

      <div className="grain absolute inset-0" />
    </div>
  )
}
