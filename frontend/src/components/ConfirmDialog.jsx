import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import Icon from './Icon'

const RING = 2 * Math.PI * 26

/**
 * Click-only confirmation. Voice cannot approve: a video or a TV in the room could say "yes".
 * Deny is focused by default, Enter does not approve, and it auto-denies when the server's
 * 60 s window runs out.
 */
export default function ConfirmDialog({ action, seconds = 60, onApprove, onDeny }) {
  const root = useRef(null)
  const card = useRef(null)
  const denyBtn = useRef(null)
  const [left, setLeft] = useState(seconds)

  useLayoutEffect(() => {
    denyBtn.current?.focus()
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tl = gsap
      .timeline()
      .from(root.current, { opacity: 0, duration: 0.25 })
      .from(card.current, { y: 30, scale: 0.96, opacity: 0, duration: 0.5, ease: 'expo.out' }, 0.05)
      .from(card.current.querySelectorAll('[data-stagger]'), { y: 10, opacity: 0, stagger: 0.06, duration: 0.35 }, 0.2)
    return () => tl.kill()
  }, [])

  useEffect(() => {
    const id = setInterval(() => setLeft((s) => s - 1), 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (left <= 0) onDeny()
  }, [left, onDeny])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onDeny()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDeny])

  const remaining = Math.max(left, 0)
  const urgent = remaining <= 10

  return (
    <div ref={root} className="fixed inset-0 z-40 flex items-center justify-center bg-abyss/80 p-4 backdrop-blur-md">
      <div
        ref={card}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-command"
        className="glass w-full max-w-lg rounded-3xl p-6 shadow-[0_0_80px_-20px_rgba(220,20,60,0.6)]"
      >
        <div data-stagger className="flex items-center gap-4">
          <div className="relative grid h-16 w-16 shrink-0 place-items-center">
            <svg viewBox="0 0 60 60" className="absolute inset-0 -rotate-90" aria-hidden>
              <circle cx="30" cy="30" r="26" fill="none" stroke="#3b0f17" strokeWidth="3" />
              <circle
                cx="30"
                cy="30"
                r="26"
                fill="none"
                stroke={urgent ? '#e8a33d' : '#ff5466'}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={RING}
                strokeDashoffset={RING * (1 - remaining / seconds)}
                style={{ transition: 'stroke-dashoffset 1s linear' }}
              />
            </svg>
            <span className={`font-display text-[22px] font-bold ${urgent ? 'text-bile' : 'text-bone'}`}>{remaining}</span>
          </div>
          <div>
            <h2 id="confirm-title" className="text-[18px] font-semibold text-bone">
              Run this on your computer?
            </h2>
            <p className="mt-0.5 text-[13px] text-ash">Only a click can approve. It is denied automatically in {remaining}s.</p>
          </div>
        </div>

        <pre
          id="confirm-command"
          data-stagger
          className="mt-5 whitespace-pre-wrap break-words rounded-xl border border-scar/60 bg-abyss/80 p-4 font-mono text-[13px] text-bone"
        >
          {action.label}
        </pre>

        <div data-stagger className="mt-6 flex justify-end gap-3">
          <button
            ref={denyBtn}
            type="button"
            onClick={onDeny}
            className="rounded-xl border border-scar/70 px-5 py-2.5 text-[14px] text-bone hover:border-ash"
          >
            Deny
          </button>
          <button
            type="button"
            onClick={onApprove}
            className="flex items-center gap-1.5 rounded-xl bg-gradient-to-b from-crimson to-[#9e0d2b] px-5 py-2.5 text-[14px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(220,20,60,0.9)] hover:brightness-110"
          >
            <Icon name="bolt" size={15} /> Run it
          </button>
        </div>
      </div>
    </div>
  )
}
