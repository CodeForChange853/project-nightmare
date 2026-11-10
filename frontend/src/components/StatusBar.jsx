import Icon, { Sigil } from './Icon'

export default function StatusBar({
  status,
  locked,
  lastAsked,
  busy = false,
  workingTarget = null,
  elapsed = 0,
  onLogout,
  onRetry,
  onSettings,
  onOpenEmails,
  onOpenDefense,
  onOpenTelemetry,
}) {
  const online = Boolean(status)
  const readonly = status?.role === 'readonly'

  return (
    <header className="flex items-center justify-between gap-3 px-4 py-3 lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Sigil
          size={34}
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
        {/* Level 5 Architect Security Clearance Badge */}
        {online && (
          <div
            className="flex items-center gap-2 rounded-full border border-[#ffd166]/80 bg-gradient-to-r from-crimson/35 via-[#ffd166]/20 to-amber-500/30 px-3 py-1 text-[11px] font-bold tracking-wider uppercase text-[#ffd166] shadow-[0_0_20px_rgba(255,209,102,0.45)]"
            title="Security Clearance: Level 5 (Architect)"
          >
            <span className="h-2 w-2 rounded-full bg-[#ffd166] shadow-[0_0_8px_#ffd166]" />
            <span>{busy ? 'L5 ARCHITECT · ACTIVE' : 'L5 ARCHITECT · IDLE'}</span>
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

        {online && busy ? (
          <span className="glass flex items-center gap-2 rounded-full border border-crimson/70 bg-crimson/20 px-3 py-1.5 text-[12px] text-ember animate-pulse shadow-[0_0_14px_rgba(220,20,60,0.5)]">
            <span className="h-2 w-2 rounded-full bg-crimson shadow-[0_0_8px_#dc143c]" />
            <span className="font-semibold text-bone">Working{workingTarget ? ` with ${workingTarget}` : '...'}</span>
            <span className="font-mono text-[11px] text-smoke">({elapsed}s)</span>
          </span>
        ) : online ? (
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

        {/* Hardware Cockpit Telemetry Pill (Phase 9A) */}
        {online && status?.telemetry && (
          <button
            type="button"
            onClick={onOpenTelemetry}
            className="glass hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] text-smoke hover:text-bone hover:border-scar transition md:flex"
            title={`System Telemetry: RAM ${status.telemetry.ram_used_gb}/${status.telemetry.ram_total_gb} GB (${status.telemetry.ram_pct}%), Battery ${status.telemetry.battery_pct ?? 'AC'}%. Tap to query hardware.`}
          >
            <Icon name="cpu" size={12} className="text-ash" />
            <span className="font-mono">{status.telemetry.ram_pct}%</span>
            {status.telemetry.battery_pct != null && (
              <>
                <span className="text-scar/60">|</span>
                <Icon name="battery" size={12} className="text-ash" />
                <span className="font-mono">{status.telemetry.battery_pct}%</span>
              </>
            )}
          </button>
        )}

        {/* Defense Co-Pilot Active Indicator & Rehearsal Launcher (Phase 8F) */}
        {online && onOpenDefense && (
          <button
            type="button"
            onClick={onOpenDefense}
            title={
              status?.defense?.status && status.defense.status !== 'inactive'
                ? `Defense Rehearsal Active: Slide ${status.defense.slide} (${status.defense.status}). Tap to open HUD.`
                : 'Academic Defense Co-Pilot & Mock Panelist'
            }
            aria-label="Defense Co-Pilot"
            className={`glass grid h-8 w-8 place-items-center rounded-full transition ${
              status?.defense?.status && status.defense.status !== 'inactive'
                ? 'border-crimson text-ember animate-pulse shadow-[0_0_12px_rgba(220,20,60,0.45)]'
                : 'text-ash hover:border-scar hover:text-bone'
            }`}
          >
            <Icon name="presentation" size={15} />
          </button>
        )}

        {online && onOpenEmails && (
          <button
            type="button"
            onClick={onOpenEmails}
            title="Real-Time Priority Email Feed (Pub/Sub)"
            aria-label="Priority Emails"
            className="glass grid h-8 w-8 place-items-center rounded-full text-ash hover:border-gold hover:text-amber-300 transition"
          >
            <Icon name="mail" size={15} />
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
