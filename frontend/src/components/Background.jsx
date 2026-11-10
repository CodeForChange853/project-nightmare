import { useEffect, useRef } from 'react'
import gsap from 'gsap'

/**
 * Ambient space behind Nightmare: blood-moon mountain backdrop, slow pools of light
 * over a dot grid, vignette, and tactical Level 5 Architect viewport perimeter frame.
 */
export default function Background() {
  const left = useRef(null)
  const right = useRef(null)
  const corona = useRef(null)
  const frameRef = useRef(null)

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

  const leftGrad = 'radial-gradient(closest-side, rgba(255,30,66,0.24), rgba(232,163,61,0.08), transparent)'
  const rightGrad = 'radial-gradient(closest-side, rgba(255,209,102,0.20), rgba(180,12,40,0.14), transparent)'
  const dotColor = 'rgba(255,209,102,0.24)'

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-abyss">
      {/* Level 5 Blood-Moon Mountain Background (nightmare_bg.png) */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat opacity-95 scale-100"
        style={{
          backgroundImage: "url('/assets/nightmare_bg.png')",
        }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/35 to-black/80" />

      <div
        ref={left}
        className="absolute -left-[15%] top-[10%] h-[80vh] w-[70vw] opacity-100"
        style={{ background: leftGrad }}
      />
      <div
        ref={right}
        className="absolute -right-[10%] -top-[20%] h-[70vh] w-[50vw] opacity-80"
        style={{ background: rightGrad }}
      />
      <div
        ref={corona}
        className="absolute left-1/2 top-0 h-[45vh] w-[80vw] -translate-x-1/2 opacity-90"
        style={{
          background:
            'radial-gradient(ellipse at 50% 0%, rgba(255,209,102,0.15), rgba(220,20,60,0.08) 55%, transparent 80%)',
        }}
      />
      <div
        className="absolute inset-0 opacity-55"
        style={{
          backgroundImage: `radial-gradient(${dotColor} 1px, transparent 1.2px)`,
          backgroundSize: '24px 24px',
          maskImage: 'radial-gradient(ellipse 74% 64% at 35% 50%, #000 12%, transparent 78%)',
          WebkitMaskImage: 'radial-gradient(ellipse 74% 64% at 35% 50%, #000 12%, transparent 78%)',
        }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.78)_100%)]" />

      {/* Tactical Viewport Perimeter HUD */}
      <div ref={frameRef} className="absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-[#ffd166]/80 to-transparent shadow-[0_0_16px_rgba(255,209,102,0.65)]" />
        <div className="absolute inset-x-0 bottom-0 h-[1px] bg-gradient-to-r from-transparent via-ember/65 to-transparent" />

        <span className="absolute left-2.5 top-2.5 h-5 w-5 rounded-tl-sm border-l-2 border-t-2 border-[#ffd166]/70" />
        <span className="absolute right-2.5 top-2.5 h-5 w-5 rounded-tr-sm border-r-2 border-t-2 border-[#ffd166]/70" />
        <span className="absolute bottom-2.5 left-2.5 h-5 w-5 rounded-bl-sm border-b-2 border-l-2 border-[#ffd166]/70" />
        <span className="absolute bottom-2.5 right-2.5 h-5 w-5 rounded-br-sm border-b-2 border-r-2 border-[#ffd166]/70" />

        <div className="hidden lg:flex absolute bottom-3 left-6 items-center gap-2 font-mono text-[9px] tracking-[0.22em] uppercase text-smoke/55">
          <span className="h-1.5 w-1.5 rounded-full bg-[#ffd166] shadow-[0_0_6px_#ffd166]" />
          SYS.CLEARANCE // LVL.05 ARCHITECT · SHELL UNRESTRICTED
        </div>
      </div>
    </div>
  )
}
