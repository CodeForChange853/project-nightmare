import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import Icon, { Sigil } from './Icon'

/**
 * Full-viewport cinematic GSAP transition triggered whenever the clearance level changes.
 * - Expanding radial shockwave from center in the tier's signature color.
 * - Biometric scanline sweep across the viewport.
 * - Bold typographic HUD banner stamp in Big Shoulders Display.
 */
export default function ClearanceTransition({ level, prevLevel, onComplete }) {
  const rootRef = useRef(null)
  const ringRef = useRef(null)
  const scanRef = useRef(null)
  const bannerRef = useRef(null)

  const isElevation = (level ?? 1) > (prevLevel ?? 1)
  const isL5 = level === 5
  const isL3 = level === 3
  const isL1 = level === 1

  const tierMeta = {
    1: {
      tag: 'LEVEL 1 // OBSERVER',
      title: isElevation ? 'OBSERVER RESTORED' : 'LOCKDOWN ENGAGED',
      sub: 'Read-only surveillance mode active · Mutations and raw shell locked',
      accent: '#dc143c',
      glow: 'rgba(220, 20, 60, 0.45)',
      border: 'border-scar/60',
    },
    3: {
      tag: 'LEVEL 3 // OPERATOR',
      title: 'OPERATOR ACCESS UNLOCKED',
      sub: 'Memory writes, allowlisted apps, and dev tasks authorized',
      accent: '#e8a33d',
      glow: 'rgba(232, 163, 61, 0.55)',
      border: 'border-amber-400/70',
    },
    5: {
      tag: 'LEVEL 5 // ARCHITECT',
      title: 'ARCHITECT OVERRIDE ENGAGED',
      sub: 'Total blood-moon eclipse · Unrestricted system and raw shell authority',
      accent: '#ffd166',
      glow: 'rgba(255, 209, 102, 0.65)',
      border: 'border-yellow-400/80',
    },
  }[level || 1]

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const t = setTimeout(onComplete, 900)
      return () => clearTimeout(t)
    }

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        onComplete,
        defaults: { ease: 'power3.out' },
      })

      // 1. Initial fade-in of transition container
      tl.fromTo(rootRef.current, { opacity: 0 }, { opacity: 1, duration: 0.15 })

      // 2. Expanding radial shockwave
      if (ringRef.current) {
        tl.fromTo(
          ringRef.current,
          { scale: 0.1, opacity: 0.9, borderWidth: '18px' },
          { scale: 3.5, opacity: 0, borderWidth: '1px', duration: 1.1, ease: 'expo.out' },
          0.05
        )
      }

      // 3. Scanline sweep (top to bottom on elevation; heavier shutter on lockdown)
      if (scanRef.current) {
        tl.fromTo(
          scanRef.current,
          { yPercent: isElevation ? -100 : 100, opacity: 0.8 },
          { yPercent: isElevation ? 120 : -120, opacity: 0, duration: 0.85, ease: 'power2.inOut' },
          0.1
        )
      }

      // 4. Banner punch-in
      if (bannerRef.current) {
        tl.fromTo(
          bannerRef.current,
          { scale: 0.88, y: isElevation ? -24 : 24, opacity: 0 },
          { scale: 1, y: 0, opacity: 1, duration: 0.45, ease: 'back.out(1.8)' },
          0.15
        )
        // Hold on screen, then cleanly exit
        tl.to(bannerRef.current, { y: isElevation ? 16 : -16, opacity: 0, duration: 0.35, ease: 'power2.in' }, 1.7)
      }

      tl.to(rootRef.current, { opacity: 0, duration: 0.25 }, 1.85)
    }, rootRef)

    return () => ctx.revert()
  }, [level, isElevation, onComplete])

  return (
    <div
      ref={rootRef}
      className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center overflow-hidden"
      aria-live="assertive"
      role="status"
    >
      {/* Background dark flash */}
      <div
        className={`absolute inset-0 transition-opacity ${
          isL5
            ? 'bg-gradient-to-b from-[#ffd166]/15 via-black/75 to-crimson/20 backdrop-blur-[3px]'
            : isL3
              ? 'bg-gradient-to-b from-amber-500/10 via-black/70 to-scab/40 backdrop-blur-[2px]'
              : 'bg-black/65 backdrop-blur-[2px]'
        }`}
      />

      {/* Radial Shockwave Ring */}
      <div
        ref={ringRef}
        className="pointer-events-none absolute h-64 w-64 rounded-full border"
        style={{
          borderColor: tierMeta.accent,
          boxShadow: `0 0 45px ${tierMeta.glow}, inset 0 0 35px ${tierMeta.glow}`,
        }}
      />

      {/* Scanline Sweep */}
      <div
        ref={scanRef}
        className="pointer-events-none absolute inset-x-0 h-28"
        style={{
          background: `linear-gradient(180deg, transparent, ${tierMeta.accent}33, ${tierMeta.accent}99, transparent)`,
          filter: `drop-shadow(0 0 12px ${tierMeta.accent})`,
        }}
      />

      {/* Typographic HUD Banner Stamp */}
      <div
        ref={bannerRef}
        className={`glass relative mx-4 max-w-xl rounded-3xl border p-6 text-center shadow-2xl ${tierMeta.border}`}
        style={{
          boxShadow: `0 0 60px -10px ${tierMeta.glow}, 0 30px 80px -20px rgba(0,0,0,0.9)`,
        }}
      >
        {/* Corner HUD reticles */}
        <span className="absolute left-2.5 top-2.5 h-3 w-3 border-l-2 border-t-2" style={{ borderColor: tierMeta.accent }} />
        <span className="absolute right-2.5 top-2.5 h-3 w-3 border-r-2 border-t-2" style={{ borderColor: tierMeta.accent }} />
        <span className="absolute bottom-2.5 left-2.5 h-3 w-3 border-b-2 border-l-2" style={{ borderColor: tierMeta.accent }} />
        <span className="absolute bottom-2.5 right-2.5 h-3 w-3 border-b-2 border-r-2" style={{ borderColor: tierMeta.accent }} />

        <div className="flex items-center justify-center gap-3">
          <Sigil size={32} clearanceLevel={level} />
          <span
            className="font-mono text-[11px] font-extrabold uppercase tracking-[0.28em]"
            style={{ color: tierMeta.accent }}
          >
            {tierMeta.tag}
          </span>
        </div>

        <h1
          className="mt-2.5 font-display text-[32px] font-extrabold uppercase tracking-[0.18em] text-bone sm:text-[38px]"
          style={{ textShadow: `0 0 24px ${tierMeta.glow}` }}
        >
          {tierMeta.title}
        </h1>

        <p className="mx-auto mt-2 max-w-[42ch] text-[13px] leading-relaxed text-ash">
          {tierMeta.sub}
        </p>

        <div className="mt-4 flex items-center justify-center gap-2 font-mono text-[10px] uppercase tracking-wider text-smoke">
          <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tierMeta.accent }} />
          <span>SECURITY CLEARANCE PROTOCOL // {level === 5 ? 'TIER 3/3' : level === 3 ? 'TIER 2/3' : 'TIER 1/3'}</span>
        </div>
      </div>
    </div>
  )
}
