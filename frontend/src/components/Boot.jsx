import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrambleTextPlugin } from 'gsap/ScrambleTextPlugin'
import { Sigil } from './Icon'

gsap.registerPlugin(ScrambleTextPlugin)

const STEPS = ['Waking up', 'Reaching the backend', 'Reading your projects', 'Opening the eye']
const MIN_MS = 1500

/**
 * Full-screen loader shown once per page load. The bar is tied to the real first /status
 * request: it creeps to 85% on its own and only finishes when `done` turns true.
 */
export default function Boot({ done, onFinished }) {
  const root = useRef(null)
  const word = useRef(null)
  const bar = useRef(null)
  const progress = useRef({ v: 0 })
  const started = useRef(performance.now())
  const [step, setStep] = useState(0)

  useLayoutEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const ctx = gsap.context(() => {
      if (!reduced) {
        gsap.to(word.current, { duration: 1.3, scrambleText: { text: 'NIGHTMARE', chars: '▓▒░█#%&?ΔΞ', speed: 0.5 } })
        gsap.to('[data-boot-ring]', { rotate: 360, duration: 6, ease: 'none', repeat: -1, transformOrigin: '50% 50%' })
        gsap.from('[data-boot-sigil]', { scale: 0.6, opacity: 0, duration: 0.9, ease: 'expo.out' })
      } else {
        word.current.textContent = 'NIGHTMARE'
      }
      gsap.to(progress.current, {
        v: 0.85,
        duration: 2.4,
        ease: 'power2.out',
        onUpdate: () => {
          const v = progress.current.v
          gsap.set(bar.current, { scaleX: v })
          setStep(Math.min(STEPS.length - 2, Math.floor(v * (STEPS.length - 1) * 1.2)))
        },
      })
    }, root)
    return () => ctx.revert()
  }, [])

  useEffect(() => {
    if (!done) return
    const wait = Math.max(0, MIN_MS - (performance.now() - started.current)) / 1000
    const tl = gsap.timeline({ delay: wait, onComplete: onFinished })
    tl.add(() => setStep(STEPS.length - 1))
      .to(progress.current, {
        v: 1,
        duration: 0.35,
        ease: 'power2.inOut',
        onUpdate: () => gsap.set(bar.current, { scaleX: progress.current.v }),
      })
      .to('[data-boot-inner]', { scale: 1.08, opacity: 0, duration: 0.45, ease: 'power2.in' }, '+=0.1')
      .to(root.current, { clipPath: 'circle(0% at 22% 50%)', duration: 0.8, ease: 'expo.inOut' }, '-=0.15')
    return () => tl.kill()
  }, [done, onFinished])

  return (
    <div
      ref={root}
      role="status"
      aria-label="Loading Nightmare"
      className="fixed inset-0 z-50 grid place-items-center bg-abyss"
      style={{ clipPath: 'circle(150% at 22% 50%)' }}
    >
      <div className="grain pointer-events-none absolute inset-0" />
      <div data-boot-inner className="flex flex-col items-center">
        <div className="relative grid h-36 w-36 place-items-center">
          <svg data-boot-ring viewBox="0 0 100 100" className="absolute inset-0" aria-hidden>
            <circle cx="50" cy="50" r="47" fill="none" stroke="#5c1a24" strokeWidth="0.6" />
            <circle
              cx="50"
              cy="50"
              r="47"
              fill="none"
              stroke="#ff5466"
              strokeWidth="1.2"
              strokeDasharray="40 255"
              strokeLinecap="round"
            />
            <circle cx="50" cy="50" r="40" fill="none" stroke="#3b0f17" strokeWidth="0.6" strokeDasharray="1 3" />
          </svg>
          <div data-boot-sigil>
            <Sigil size={72} className="drop-shadow-[0_0_24px_rgba(220,20,60,0.7)]" />
          </div>
        </div>
        <p
          ref={word}
          className="mt-8 font-display text-[44px] font-extrabold leading-none tracking-[0.28em] text-bone"
          aria-hidden
        >
          {' '}
        </p>
        <div className="mt-6 h-px w-56 overflow-hidden bg-vein">
          <div ref={bar} className="h-full origin-left scale-x-0 bg-gradient-to-r from-crimson to-ember" />
        </div>
        <p className="mt-3 text-[12px] text-smoke">{STEPS[step]}</p>
      </div>
    </div>
  )
}
