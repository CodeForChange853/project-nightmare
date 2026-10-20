import { useEffect, useRef } from 'react'
import gsap from 'gsap'

/**
 * The core: a blood-moon eye inside a ring of waveform spikes. Each mode changes how hard
 * the ring moves and how wide the pupil opens, so you can read Nightmare's state at a glance:
 * listening = wide awake, thinking = pinned pupil with a scanning arc, confirm = dilated.
 */
const MODES = {
  idle: { amp: 0.2, pupil: 0.13, speed: 0.6, glow: 0.6, lid: 0 },
  listening: { amp: 1, pupil: 0.34, speed: 2.4, glow: 1, lid: 0 },
  thinking: { amp: 0.42, pupil: 0.06, speed: 1.2, glow: 0.85, lid: 0 },
  speaking: { amp: 0.62, pupil: 0.2, speed: 1.8, glow: 0.9, lid: 0 },
  confirm: { amp: 0.32, pupil: 0.5, speed: 0.9, glow: 1, lid: 0 },
  offline: { amp: 0.05, pupil: 0.04, speed: 0.2, glow: 0.18, lid: 0 },
  // eyelids almost shut, a barely moving ring and a dim glow that slowly breathes
  sleep: { amp: 0.06, pupil: 0.03, speed: 0.25, glow: 0.3, lid: 0.93 },
}
const SPIKES = 220
const TAU = Math.PI * 2

export default function Orb({ mode = 'idle', className = '', track = true }) {
  const canvasRef = useRef(null)
  const live = useRef({ ...MODES.idle, mode, lookX: 0, lookY: 0, lid: 0, flare: 0 })

  // ease every visual parameter toward the new mode
  useEffect(() => {
    const target = MODES[mode] ?? MODES.idle
    live.current.mode = mode
    // falling asleep is slow and heavy; everything else snaps to attention
    const slow = mode === 'sleep'
    const tween = gsap.to(live.current, { ...target, duration: slow ? 2.2 : 0.7, ease: slow ? 'power2.inOut' : 'power3.out' })
    // a quick flare when something happens, so the change is noticed
    const flare = gsap.fromTo(live.current, { flare: 1 }, { flare: 0, duration: 1.1, ease: 'power2.out' })
    return () => {
      tween.kill()
      flare.kill()
    }
  }, [mode])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const s = live.current
    let t = 0

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.max(1, Math.floor(canvas.clientWidth * dpr))
      canvas.height = Math.max(1, Math.floor(canvas.clientHeight * dpr))
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    // the pupil follows the pointer a little
    const lookX = gsap.quickTo(s, 'lookX', { duration: 0.8, ease: 'power3.out' })
    const lookY = gsap.quickTo(s, 'lookY', { duration: 0.8, ease: 'power3.out' })
    const onMove = (e) => {
      if (!track || reduced) return
      const r = canvas.getBoundingClientRect()
      const dx = e.clientX - (r.left + r.width / 2)
      const dy = e.clientY - (r.top + r.height / 2)
      const d = Math.hypot(dx, dy) || 1
      const k = Math.min(1, d / 600)
      lookX((dx / d) * k)
      lookY((dy / d) * k)
    }
    window.addEventListener('pointermove', onMove)

    // occasional blink while idle or speaking
    let blinkCall
    const scheduleBlink = () => {
      blinkCall = gsap.delayedCall(gsap.utils.random(4, 9), () => {
        if (s.mode === 'idle' || s.mode === 'speaking') {
          gsap.to(s, { lid: 1, duration: 0.08, ease: 'power2.in', yoyo: true, repeat: 1 })
        }
        scheduleBlink()
      })
    }
    if (!reduced) scheduleBlink()

    const draw = () => {
      t += (reduced ? 0.12 : 1) * s.speed * 0.016 * gsap.ticker.deltaRatio()
      const w = canvas.width
      const h = canvas.height
      const cx = w / 2
      const cy = h / 2
      const R = Math.min(w, h) / 2
      const breath = s.mode === 'sleep' ? 0.12 * Math.sin(t * 6) : 0
      const glow = Math.min(1.4, s.glow + s.flare * 0.5 + breath)
      ctx.clearRect(0, 0, w, h)

      // halo
      const halo = ctx.createRadialGradient(cx, cy, R * 0.25, cx, cy, R)
      halo.addColorStop(0, `rgba(220,20,60,${0.26 * glow})`)
      halo.addColorStop(0.55, `rgba(110,8,26,${0.1 * glow})`)
      halo.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = halo
      ctx.fillRect(0, 0, w, h)

      // spike ring
      const rRing = R * 0.62
      const scanAt = (t * 2.6) % TAU
      const dim = new Path2D()
      const hot = new Path2D()
      for (let i = 0; i < SPIKES; i++) {
        const a = (i / SPIKES) * TAU - Math.PI / 2
        let v =
          Math.sin(a * 3 + t * 1.7) * 0.5 + Math.sin(a * 7 - t * 1.1) * 0.3 + Math.sin(a * 17 + t * 2.9) * 0.2
        v = ((v + 1) / 2) ** 2
        if (s.mode === 'listening' && !reduced) v += Math.random() * 0.35
        if (s.mode === 'speaking') v *= 0.55 + 0.45 * Math.abs(Math.sin(t * 7 + a))
        if (s.mode === 'thinking') {
          let d = Math.abs(((a + Math.PI / 2) % TAU) - scanAt)
          d = Math.min(d, TAU - d)
          v += 1.4 * Math.exp(-(d * d) / 0.06)
        }
        const energy = v * s.amp
        const len = R * 0.015 + energy * R * 0.26
        const cos = Math.cos(a)
        const sin = Math.sin(a)
        const path = energy > 0.32 ? hot : dim
        path.moveTo(cx + cos * (rRing - len * 0.25), cy + sin * (rRing - len * 0.25))
        path.lineTo(cx + cos * (rRing + len), cy + sin * (rRing + len))
      }
      ctx.lineCap = 'round'
      ctx.lineWidth = Math.max(1, R * 0.0075)
      ctx.strokeStyle = `rgba(220,20,60,${0.35 + 0.3 * glow})`
      ctx.stroke(dim)
      ctx.save()
      ctx.shadowColor = '#ff5466'
      ctx.shadowBlur = R * 0.05
      ctx.strokeStyle = '#ff6a7a'
      ctx.stroke(hot)
      ctx.restore()

      // inner hairline ring, dashed
      ctx.save()
      ctx.setLineDash([R * 0.01, R * 0.03])
      ctx.lineDashOffset = -t * R * 0.04
      ctx.strokeStyle = 'rgba(255,84,102,0.28)'
      ctx.lineWidth = Math.max(1, R * 0.004)
      ctx.beginPath()
      ctx.arc(cx, cy, rRing * 0.84, 0, TAU)
      ctx.stroke()
      ctx.restore()

      // the moon
      const rS = R * 0.34 * (1 + Math.sin(t * 1.4) * 0.018 + s.flare * 0.04)
      ctx.save()
      ctx.shadowColor = `rgba(220,20,60,${0.75 * Math.min(1, glow)})`
      ctx.shadowBlur = R * 0.16
      const body = ctx.createRadialGradient(cx - rS * 0.35, cy - rS * 0.4, rS * 0.04, cx, cy, rS)
      body.addColorStop(0, '#ffc2c8')
      body.addColorStop(0.16, '#ff5466')
      body.addColorStop(0.52, '#b0102e')
      body.addColorStop(0.86, '#4a0611')
      body.addColorStop(1, '#1c0207')
      ctx.fillStyle = body
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.fill()
      ctx.restore()

      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.clip()

      // slow veins under the surface
      ctx.strokeStyle = 'rgba(40,0,8,0.4)'
      ctx.lineWidth = Math.max(1, rS * 0.018)
      for (let k = 0; k < 6; k++) {
        const base = (k / 6) * TAU + t * 0.15
        ctx.beginPath()
        ctx.moveTo(cx + Math.cos(base) * rS * 1.05, cy + Math.sin(base) * rS * 1.05)
        ctx.quadraticCurveTo(
          cx + Math.cos(base + 0.6) * rS * 0.55,
          cy + Math.sin(base + 0.6) * rS * 0.55,
          cx + Math.cos(base + 0.25) * rS * 0.4,
          cy + Math.sin(base + 0.25) * rS * 0.4,
        )
        ctx.stroke()
      }

      // iris shadow + slit pupil
      const px = cx + s.lookX * rS * 0.24
      const py = cy + s.lookY * rS * 0.16
      const iris = ctx.createRadialGradient(px, py, rS * 0.05, px, py, rS * 0.75)
      iris.addColorStop(0, 'rgba(30,0,6,0.55)')
      iris.addColorStop(1, 'rgba(30,0,6,0)')
      ctx.fillStyle = iris
      ctx.fillRect(cx - rS, cy - rS, rS * 2, rS * 2)

      const ph = rS * 0.8
      const pw = rS * s.pupil * 2
      ctx.save()
      ctx.shadowColor = 'rgba(255,84,102,0.55)'
      ctx.shadowBlur = rS * 0.12
      ctx.fillStyle = '#070203'
      ctx.beginPath()
      ctx.moveTo(px, py - ph)
      ctx.quadraticCurveTo(px + pw, py, px, py + ph)
      ctx.quadraticCurveTo(px - pw, py, px, py - ph)
      ctx.fill()
      ctx.restore()

      // wet highlight
      ctx.fillStyle = 'rgba(255,235,238,0.32)'
      ctx.beginPath()
      ctx.ellipse(cx - rS * 0.42, cy - rS * 0.46, rS * 0.16, rS * 0.08, -0.6, 0, TAU)
      ctx.fill()

      // eyelids for the blink
      if (s.lid > 0.01) {
        ctx.fillStyle = '#12030a'
        ctx.fillRect(cx - rS, cy - rS, rS * 2, rS * s.lid)
        ctx.fillRect(cx - rS, cy + rS - rS * s.lid, rS * 2, rS * s.lid)
      }
      ctx.restore()
    }

    gsap.ticker.add(draw)
    return () => {
      gsap.ticker.remove(draw)
      blinkCall?.kill()
      ro.disconnect()
      window.removeEventListener('pointermove', onMove)
    }
  }, [track])

  return <canvas ref={canvasRef} className={`block h-full w-full ${className}`} role="img" aria-label={`Nightmare is ${mode}`} />
}
