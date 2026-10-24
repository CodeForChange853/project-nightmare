import { useEffect, useState } from 'react'
import Icon, { Sigil } from './Icon'

export default function StatusBar({
  status,
  locked,
  lastAsked,
  onLogout,
  onRetry,
  onSettings,
  onOpenClearance,
  onLockdown,
}) {
  const online = Boolean(status)
  const readonly = status?.role === 'readonly'
  const clearanceLevel = status?.clearance_level ?? 1

  // Live countdown timer for inactivity decay
  const [remaining, setRemaining] = useState(status?.clearance_expires_in ?? null)
  useEffect(() => {
    setRemaining(status?.clearance_expires_in ?? null)
  }, [status?.clearance_expires_in, status?.clearance_level])

  useEffect(() => {
    if (remaining == null || remaining <= 0) return
    const id = setInterval(() => {
      setRemaining((r) => (r > 0 ? r - 1 : 0))
    }, 1000)
    return () => clearInterval(id)
  }, [remaining])

  const formatCountdown = (secs) => {
    if (secs == null || secs <= 0) return null
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  const timeoutTotal = status?.clearance_timeout || (clearanceLevel === 5 ? 600 : clearanceLevel === 3 ? 1800 : null)
  const pct = timeoutTotal && remaining ? Math.max(0, Math.min(100, (remaining / timeoutTotal) * 100)) : 0

  return (
    <header className="flex items-center justify-between gap-3 px-4 py-3 lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Sigil
          size={34}
          clearanceLevel={clearanceLevel}
          className="shrink-0 drop-shadow-[0_0_12px_rgba(220,20,60,0.55)] transition-all duration-700"
        />
        <div className="leading-none">
          <p className="font-display text-[19px] font-extrabold uppercase tracking-[0.22em] text-bone">Nightmare</p>
          <p className="mt-1 text-[11px] text-smoke">Local voice agent</p>
        </div>
      </div>

      {lastAsked && (
        <p className="glass hidden max-w-[42ch] truncate rounded-full px-4 py-1.5 text-[12px] text-ash md:block" title={lastAsked}>
          <span className="text-smoke">You asked </span>
          <span className="text-bone">{lastAsked}</span>
        </p>
      )}

      <div className="flex shrink-0 items-center gap-2">
        {/* Persistent 3-Tier Security Clearance Badge */}
        {online && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onOpenClearance}
              className={`relative flex items-center gap-2 overflow-hidden rounded-full px-3 py-1 text-[11px] font-bold tracking-wider uppercase transition-all ${
                clearanceLevel === 5
                  ? 'border border-[#ffd166]/80 bg-gradient-to-r from-crimson/35 via-[#ffd166]/20 to-amber-500/30 text-[#ffd166] shadow-[0_0_20px_rgba(255,209,102,0.45)]'
                  : clearanceLevel === 3
                    ? 'border border-amber-400/70 bg-amber-500/20 text-amber-300 shadow-[0_0_14px_rgba(232,163,61,0.3)]'
                    : 'border border-scar/50 bg-scar/15 text-smoke hover:border-scar/80 hover:text-bone'
              }`}
              title={`Security Clearance: Level ${clearanceLevel}. Tap to elevate or switch tier.`}
            >
              <span
                className={`h-2 w-2 rounded-full transition-colors ${
                  clearanceLevel === 5
                    ? 'bg-[#ffd166] shadow-[0_0_8px_#ffd166]'
                    : clearanceLevel === 3
                      ? 'bg-amber-400 shadow-[0_0_6px_#fbbf24]'
                      : 'bg-smoke/60'
                }`}
              />
              <span>
                {clearanceLevel === 5
                  ? 'L5 ARCHITECT'
                  : clearanceLevel === 3
                    ? 'L3 OPERATOR'
                    : 'L1 OBSERVER'}
              </span>

              {/* Decay Countdown Timer */}
              {remaining != null && remaining > 0 && (
                <span className="font-mono text-[10px] opacity-85">
                  ({formatCountdown(remaining)})
                </span>
              )}

              {/* Inactivity Decay Progress Bar */}
              {clearanceLevel > 1 && remaining != null && (
                <span
                  className="pointer-events-none absolute bottom-0 left-0 h-[2px] transition-all duration-1000"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: clearanceLevel === 5 ? '#ffd166' : '#fbbf24',
                    boxShadow: clearanceLevel === 5 ? '0 0 6px #ffd166' : '0 0 4px #fbbf24',
                  }}
                />
              )}
            </button>

            {/* Quick 1-click Lockdown Button when elevated */}
            {clearanceLevel > 1 && onLockdown && (
              <button
                type="button"
                onClick={onLockdown}
                title="Immediate Lockdown (drop to Level 1 Observer)"
                aria-label="Immediate Lockdown"
                className="glass grid h-7 w-7 place-items-center rounded-full text-smoke hover:border-crimson hover:text-ember"
              >
                <Icon name="x" size={12} />
              </button>
            )}
          </div>
        )}

        {readonly && (
          <span
            className="rounded-full border border-bile/40 bg-bile/10 px-2.5 py-1 text-[11px] text-bile"
            title="Phone PIN session: Nightmare can read and answer, but cannot open or run anything"
          >
            Read-only
          </span>
        )}

        {online ? (
          <span className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ash">
            <span className="pulse-dot h-2 w-2 rounded-full bg-crimson" />
            Online
            <span className="hidden text-smoke sm:inline">with {status.llm}</span>
          </span>
        ) : locked ? (
          <span className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ash">
            <Icon name="lock" size={13} /> Locked
          </span>
        ) : (
          <button
            type="button"
            onClick={onRetry}
            className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ember hover:text-bone"
          >
            <span className="h-2 w-2 rounded-full bg-smoke" />
            Backend offline
            <Icon name="refresh" size={13} />
          </button>
        )}

        {online && !readonly && (
          <button
            type="button"
            onClick={onSettings}
            title="Settings: apps and tasks"
            aria-label="Settings"
            className="glass grid h-8 w-8 place-items-center rounded-full text-ash hover:text-ember"
          >
            <Icon name="sliders" size={15} />
          </button>
        )}

        {status?.auth_mode === 'session' && (
          <button
            type="button"
            onClick={onLogout}
            title="Lock Nightmare"
            aria-label="Lock Nightmare"
            className="glass grid h-8 w-8 place-items-center rounded-full text-ash hover:text-ember"
          >
            <Icon name="lock" size={15} />
          </button>
        )}
      </div>
    </header>
  )
}
