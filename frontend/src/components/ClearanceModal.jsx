import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { elevateClearance, lockdownClearance } from '../api'
import Icon, { Sigil } from './Icon'

/**
 * 3-Tier Security Clearance Control Deck.
 * Allows quick tier switching between Level 1 (Observer), Level 3 (Operator), and Level 5 (Architect).
 * Preserves canonical prompt strings for voice & test compatibility.
 */
export default function ClearanceModal({
  level: initialLevel = 3,
  currentLevel = 1,
  onClose,
  onSuccess,
}) {
  const root = useRef(null)
  const card = useRef(null)
  const inputRef = useRef(null)

  const [activeTier, setActiveTier] = useState(initialLevel === 1 ? 3 : initialLevel)
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isL5 = activeTier === 5
  const isL3 = activeTier === 3

  const title = isL5 ? 'LEVEL 5 (ARCHITECT)' : 'LEVEL 3 (OPERATOR)'
  const promptText = isL5
    ? 'Opening Nightmare Level 5 access... please write the password'
    : 'Opening Nightmare Level 3 access. Please enter your PIN.'
  const placeholder = isL5 ? 'Enter Level 5 Password...' : 'Enter 6-digit PIN...'

  useLayoutEffect(() => {
    inputRef.current?.focus()
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tl = gsap
      .timeline()
      .from(root.current, { opacity: 0, duration: 0.2 })
      .from(card.current, { y: 25, scale: 0.95, opacity: 0, duration: 0.45, ease: 'expo.out' }, 0.05)
    return () => tl.kill()
  }, [])

  useEffect(() => {
    setValue('')
    setError('')
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [activeTier])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const secret = value.trim()
    if (!secret || busy) return
    setError('')
    setBusy(true)
    try {
      const res = await elevateClearance(activeTier, secret)
      if (res.ok) {
        onSuccess(activeTier)
      } else {
        setError('Elevation failed.')
      }
    } catch (err) {
      setError(err.message || 'Verification failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleLockdown = async () => {
    if (busy) return
    setBusy(true)
    try {
      await lockdownClearance()
      onSuccess(1)
    } catch (err) {
      setError(err.message || 'Lockdown failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      ref={root}
      className="fixed inset-0 z-50 flex items-center justify-center bg-abyss/85 p-4 backdrop-blur-md"
      onClick={(e) => {
        if (e.target === root.current && !busy) onClose()
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        ref={card}
        className={`glass relative w-full max-w-lg overflow-hidden rounded-3xl border p-6 shadow-2xl transition-all duration-500 ${
          isL5
            ? 'border-[#ffd166]/70 shadow-[0_0_60px_rgba(255,209,102,0.3)]'
            : isL3
              ? 'border-amber-400/60 shadow-[0_0_40px_rgba(232,163,61,0.25)]'
              : 'border-scar/60 shadow-[0_0_35px_rgba(220,20,60,0.2)]'
        }`}
      >
        {/* Ambient Corner Flare */}
        <div
          className={`pointer-events-none absolute -right-20 -top-20 h-52 w-52 rounded-full blur-3xl transition-colors duration-700 ${
            isL5 ? 'bg-[#ffd166]/25' : isL3 ? 'bg-amber-500/22' : 'bg-crimson/20'
          }`}
        />

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <Sigil size={36} clearanceLevel={activeTier} className="shrink-0" />
            <div>
              <p
                className={`font-display text-[20px] font-extrabold uppercase tracking-widest transition-colors ${
                  isL5 ? 'text-[#ffd166]' : isL3 ? 'text-amber-300' : 'text-bone'
                }`}
              >
                {title}
              </p>
              <p className="font-mono text-[11px] uppercase tracking-wider text-smoke">
                Security Clearance Protocol // Current: Level {currentLevel}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
            className="glass grid h-8 w-8 place-items-center rounded-full text-ash hover:text-bone disabled:opacity-50"
          >
            <Icon name="x" size={14} />
          </button>
        </div>

        {/* 3-Tier Selector Ribbon */}
        <div className="mt-5 grid grid-cols-3 gap-1.5 rounded-2xl border border-scar/40 bg-black/40 p-1">
          {/* Level 1 Button */}
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (currentLevel > 1) {
                handleLockdown()
              } else {
                onClose()
              }
            }}
            className={`flex flex-col items-center justify-center rounded-xl py-2 transition-all ${
              currentLevel === 1 && !isL3 && !isL5
                ? 'bg-scar/50 text-bone shadow-[inset_0_1px_0_rgba(255,120,135,0.2)]'
                : 'text-smoke hover:bg-vein/30 hover:text-ash'
            }`}
          >
            <span className="font-display text-[15px] font-bold uppercase tracking-wider">L1 Observer</span>
            <span className="text-[10px] text-smoke">
              {currentLevel > 1 ? 'Engage Lockdown' : 'Active (Read-only)'}
            </span>
          </button>

          {/* Level 3 Button */}
          <button
            type="button"
            disabled={busy}
            onClick={() => setActiveTier(3)}
            className={`flex flex-col items-center justify-center rounded-xl py-2 transition-all ${
              isL3
                ? 'border border-amber-400/60 bg-amber-500/20 text-amber-300 shadow-[0_0_15px_rgba(232,163,61,0.25)]'
                : 'text-smoke hover:bg-vein/30 hover:text-ash'
            }`}
          >
            <span className="font-display text-[15px] font-bold uppercase tracking-wider">L3 Operator</span>
            <span className="text-[10px] text-smoke">
              {currentLevel === 3 ? 'Active (PIN)' : 'Unlock with PIN'}
            </span>
          </button>

          {/* Level 5 Button */}
          <button
            type="button"
            disabled={busy}
            onClick={() => setActiveTier(5)}
            className={`flex flex-col items-center justify-center rounded-xl py-2 transition-all ${
              isL5
                ? 'border border-[#ffd166]/70 bg-[#ffd166]/15 text-[#ffd166] shadow-[0_0_20px_rgba(255,209,102,0.3)]'
                : 'text-smoke hover:bg-vein/30 hover:text-ash'
            }`}
          >
            <span className="font-display text-[15px] font-bold uppercase tracking-wider">L5 Architect</span>
            <span className="text-[10px] text-smoke">
              {currentLevel === 5 ? 'Active (Pass)' : 'Unlock with Pass'}
            </span>
          </button>
        </div>

        {/* Tier Capabilities Summary Card */}
        <div
          className={`mt-4 rounded-2xl border p-3.5 text-[12px] leading-relaxed transition-colors ${
            isL5
              ? 'border-[#ffd166]/30 bg-[#ffd166]/5 text-[#ffd166]/90'
              : 'border-amber-500/30 bg-amber-500/5 text-amber-200/90'
          }`}
        >
          <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-wider">
            <span
              className={`h-1.5 w-1.5 rounded-full ${isL5 ? 'bg-[#ffd166]' : 'bg-amber-400'}`}
            />
            {isL5 ? 'Level 5 Scope (10-min decay)' : 'Level 3 Scope (30-min decay)'}
          </div>
          <p className="mt-1 text-[12px] text-ash">
            {isL5
              ? 'Total root access: Raw shell commands, deep filesystem execution, and unrestricted system mutations.'
              : 'Operator access: Allows reminders, memory writes (facts/notes), allowlisted apps in apps.json, and dev tasks.'}
          </p>
        </div>

        <p className="mt-4 text-[13px] leading-relaxed text-bone">{promptText}</p>

        {/* Secret Submission Form */}
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <input
              ref={inputRef}
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={placeholder}
              disabled={busy}
              autoComplete={isL5 ? 'current-password' : 'one-time-code'}
              className={`w-full rounded-2xl border bg-black/65 px-4 py-3 text-[14px] text-bone placeholder:text-smoke/60 focus:outline-none transition-all ${
                isL5
                  ? 'border-[#ffd166]/40 focus:border-[#ffd166] focus:shadow-[0_0_20px_rgba(255,209,102,0.3)]'
                  : 'border-amber-500/40 focus:border-amber-400 focus:shadow-[0_0_18px_rgba(232,163,61,0.25)]'
              }`}
            />
          </div>

          {error && (
            <p className="text-[12px] text-ember" role="alert">
              {error}
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            {currentLevel > 1 ? (
              <button
                type="button"
                onClick={handleLockdown}
                disabled={busy}
                className="rounded-xl px-3 py-2 text-[12px] text-smoke hover:text-ember transition-colors"
              >
                Lock down to L1
              </button>
            ) : (
              <div />
            )}

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={onClose}
                disabled={busy}
                className="rounded-xl px-4 py-2 text-[13px] text-ash hover:text-bone disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy || !value.trim()}
                className={`flex items-center gap-2 rounded-xl px-5 py-2 text-[13px] font-semibold text-black transition-all disabled:opacity-40 ${
                  isL5
                    ? 'bg-gradient-to-r from-[#ffd166] to-amber-300 hover:brightness-110 shadow-[0_0_22px_rgba(255,209,102,0.4)]'
                    : 'bg-gradient-to-r from-amber-400 to-amber-300 hover:brightness-110 shadow-[0_0_18px_rgba(232,163,61,0.35)]'
                }`}
              >
                {busy ? (
                  <>
                    <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-black" />
                    Verifying...
                  </>
                ) : (
                  `Elevate to Level ${activeTier}`
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
