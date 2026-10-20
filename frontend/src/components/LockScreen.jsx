import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import Orb from './Orb'

export default function LockScreen({ pin, setPin, error, busy, onSubmit }) {
  const card = useRef(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const t = gsap.from(card.current, { y: 24, opacity: 0, duration: 0.7, ease: 'power3.out' })
    return () => t.kill()
  }, [])

  // shake on a wrong PIN, so the failure is felt as well as read
  useEffect(() => {
    if (!error || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const t = gsap.fromTo(card.current, { x: 0 }, { keyframes: { x: [-10, 9, -6, 4, 0] }, duration: 0.45, ease: 'power2.out' })
    return () => t.kill()
  }, [error])

  return (
    <main className="grid flex-1 place-items-center px-4 pb-10">
      <section ref={card} className="glass w-full max-w-sm rounded-3xl p-7 text-center">
        <div className="mx-auto -mt-2 h-40 w-40">
          <Orb mode={error ? 'confirm' : busy ? 'thinking' : 'idle'} />
        </div>
        <h1 className="mt-2 font-display text-[30px] font-bold uppercase tracking-[0.14em] text-bone">Locked</h1>
        <p className="mx-auto mt-2 max-w-[30ch] text-[13px] leading-relaxed text-ash">
          Enter the PIN from <code className="font-mono text-[12px] text-bone">NIGHTMARE_PIN</code> in{' '}
          <code className="font-mono text-[12px] text-bone">backend/.env</code> to start a session.
        </p>
        <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3 text-left">
          <label htmlFor="pin" className="sr-only">
            PIN or token
          </label>
          <input
            id="pin"
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            placeholder="PIN or token"
            autoFocus
            autoComplete="current-password"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'pin-error' : undefined}
            className="rounded-xl border border-scar/70 bg-abyss/70 px-4 py-3 text-center text-[15px] tracking-[0.3em] text-bone outline-none placeholder:tracking-normal placeholder:text-smoke focus:border-ember"
          />
          {error && (
            <p id="pin-error" className="text-center text-[12px] text-ember">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || !pin.trim()}
            className="rounded-xl bg-gradient-to-b from-crimson to-[#9e0d2b] px-4 py-3 text-[14px] font-semibold text-white shadow-[0_10px_30px_-10px_rgba(220,20,60,0.8)] hover:brightness-110 disabled:opacity-40"
          >
            {busy ? 'Checking…' : 'Unlock'}
          </button>
        </form>
      </section>
    </main>
  )
}
