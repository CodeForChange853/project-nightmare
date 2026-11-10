import { useEffect, useRef } from 'react'
import gsap from 'gsap'

/**
 * The Crimson Cosmic Eye Sigil — Nightmare's living astral core.
 * Inspired by `frontend/public/assets/Crimson Cosmic Eye Sigil.png`:
 * - Volumetric Crimson-Gold Nebula & Fog Light that erupts when holding Space or the Mic button (`listening`).
 * - Tilted elliptical golden planetary orbits with dark obsidian moons lit by blazing crescent eclipse rims.
 * - Concentric obsidian & gilded astrolabe rings inscribed with counter-rotating glowing arcane runes.
 * - Almond-shaped gothic filigree eyelid arches framing the circular astrolabe.
 * - Deep 3D glossy eyeball with branching crimson vascular iris filaments, a white-hot/golden-rimmed vertical
 *   cat-slit pupil, and a multi-pane curved wet glass cornea highlight.
 */
const MODES = {
  // Calm, living cosmic idle state: slow breathing iris pulse, drifting runes, gentle nebula mist
  idle: { amp: 0.2, pupil: 0.085, speed: 0.55, glow: 0.68, lid: 0, fog: 0.24 },
  // Holding Space or Mic button: Volumetric Fog Light ignites across the sigil & stage
  listening: { amp: 1.0, pupil: 0.175, speed: 2.35, glow: 1.38, lid: 0, fog: 1.0 },
  thinking: { amp: 0.46, pupil: 0.045, speed: 1.45, glow: 0.96, lid: 0, fog: 0.52 },
  speaking: { amp: 0.68, pupil: 0.135, speed: 1.85, glow: 1.08, lid: 0, fog: 0.68 },
  confirm: { amp: 0.36, pupil: 0.24, speed: 0.95, glow: 1.15, lid: 0, fog: 0.6 },
  offline: { amp: 0.04, pupil: 0.035, speed: 0.18, glow: 0.2, lid: 0, fog: 0.05 },
  // Deep idle / sleep standby: eyelids nearly shut, calm ember breathing
  sleep: { amp: 0.06, pupil: 0.03, speed: 0.24, glow: 0.36, lid: 0.9, fog: 0.14 },
}

const SPIKES = 160
const TAU = Math.PI * 2

// Pre-seeded deterministic cosmic nebula clouds, ember motes, and vascular iris fibers
const NEBULA_CLOUDS = Array.from({ length: 12 }, (_, i) => ({
  baseAngle: (i / 12) * TAU + (i % 2) * 0.22,
  dist: 0.42 + ((i * 37) % 100) / 220,
  radius: 0.28 + ((i * 53) % 100) / 320,
  speed: (i % 2 === 0 ? 1 : -1) * (0.08 + (i % 5) * 0.025),
  phase: i * 1.15,
}))

const EMBER_MOTES = Array.from({ length: 28 }, (_, i) => ({
  angle: (i / 28) * TAU + ((i * 19) % 10) * 0.06,
  dist: 0.36 + ((i * 73) % 100) / 165,
  size: 0.0045 + ((i * 29) % 100) / 14000,
  speed: 0.12 + ((i * 41) % 100) / 450,
  drift: (i % 2 === 0 ? 1 : -1) * 0.18,
  isGold: i % 3 !== 0,
}))

const IRIS_FIBERS = Array.from({ length: 44 }, (_, i) => ({
  angle: (i / 44) * TAU,
  wobble: 0.06 + ((i * 31) % 100) / 900,
  freq: 2 + (i % 3),
  phase: i * 0.77,
  hasBranch: i % 2 === 0,
  branchDir: i % 4 === 0 ? 1 : -1,
  thickness: 0.75 + ((i * 17) % 100) / 140,
}))

// Procedural vector rune strokes (normalized in [-1, 1] box) for the astrolabe ring
const RUNE_GLYPHS = [
  [[-0.3, -0.8, -0.3, 0.8], [-0.3, -0.6, 0.5, -0.1], [-0.3, 0.0, 0.5, 0.5]],
  [[-0.5, -0.8, 0.0, 0.8], [0.5, -0.8, 0.0, 0.8], [-0.4, -0.1, 0.4, -0.1]],
  [[0.0, -0.8, 0.0, 0.8], [-0.5, -0.3, 0.5, 0.3], [-0.5, 0.3, 0.5, -0.3]],
  [[-0.4, -0.8, 0.4, -0.2], [0.4, -0.2, -0.4, 0.4], [-0.4, 0.4, 0.4, 0.8]],
  [[-0.5, -0.7, -0.5, 0.7], [0.5, -0.7, 0.5, 0.7], [-0.5, 0.0, 0.5, 0.0]],
  [[0.0, -0.8, -0.5, 0.0], [-0.5, 0.0, 0.0, 0.8], [0.0, 0.8, 0.5, 0.0], [0.5, 0.0, 0.0, -0.8]],
  [[-0.4, -0.8, -0.4, 0.8], [-0.4, -0.8, 0.4, -0.3], [0.4, -0.3, -0.4, 0.1], [-0.4, 0.1, 0.5, 0.8]],
  [[-0.5, -0.6, 0.5, -0.6], [0.0, -0.6, 0.0, 0.8], [-0.4, 0.2, 0.4, 0.2]],
]

export default function Orb({ mode = 'idle', className = '', track = true }) {
  const canvasRef = useRef(null)
  const live = useRef({
    ...MODES.idle,
    mode,
    lookX: 0,
    lookY: 0,
    lid: 0,
    flare: 0,
    tier3: 0,
    tier5: 1,
    tierFlare: 0,
  })

  // Ease every visual parameter (including volumetric fog light) toward the new mode
  useEffect(() => {
    const target = MODES[mode] ?? MODES.idle
    live.current.mode = mode
    const slow = mode === 'sleep'
    const isListening = mode === 'listening'
    const tween = gsap.to(live.current, {
      ...target,
      duration: slow ? 2.0 : isListening ? 0.42 : 0.68,
      ease: slow ? 'power2.inOut' : 'power3.out',
    })
    const flare = gsap.fromTo(
      live.current,
      { flare: isListening ? 1.35 : 0.85 },
      { flare: 0, duration: isListening ? 1.25 : 0.95, ease: 'power2.out' }
    )
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
    let idleClock = 0

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.max(1, Math.floor(canvas.clientWidth * dpr))
      canvas.height = Math.max(1, Math.floor(canvas.clientHeight * dpr))
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    // Subtle pointer tracking + autonomous idle micro-saccades when pointer is still
    let lastPointerMoveAt = performance.now()
    const lookX = gsap.quickTo(s, 'lookX', { duration: 0.75, ease: 'power3.out' })
    const lookY = gsap.quickTo(s, 'lookY', { duration: 0.75, ease: 'power3.out' })
    const onMove = (e) => {
      if (!track || reduced) return
      lastPointerMoveAt = performance.now()
      const r = canvas.getBoundingClientRect()
      const dx = e.clientX - (r.left + r.width / 2)
      const dy = e.clientY - (r.top + r.height / 2)
      const d = Math.hypot(dx, dy) || 1
      const k = Math.min(1, d / 560)
      lookX((dx / d) * k)
      lookY((dy / d) * k)
    }
    window.addEventListener('pointermove', onMove)

    // Natural blink while idle or speaking
    let blinkCall
    const scheduleBlink = () => {
      blinkCall = gsap.delayedCall(gsap.utils.random(4.2, 8.8), () => {
        if (s.mode === 'idle' || s.mode === 'speaking') {
          gsap.to(s, { lid: 1, duration: 0.085, ease: 'power2.in', yoyo: true, repeat: 1 })
        }
        scheduleBlink()
      })
    }
    if (!reduced) scheduleBlink()

    // Helper: draw tilted golden planetary orbit arc + eclipsed moons
    const drawPlanetaryOrbit = (cx, cy, rx, ry, tiltRad, isFrontPass, weight, time, fogIntensity) => {
      if (weight <= 0.02) return
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(tiltRad)

      const startAng = isFrontPass ? 0 : Math.PI
      const endAng = isFrontPass ? Math.PI : TAU

      // Outer golden orbital glow
      ctx.strokeStyle = `rgba(255, 195, 85, ${(0.36 + fogIntensity * 0.28) * weight})`
      ctx.lineWidth = Math.max(1, rx * 0.011)
      ctx.beginPath()
      ctx.ellipse(0, 0, rx, ry, 0, startAng, endAng)
      ctx.stroke()

      // Secondary inscribed rune-dashed orbital track
      ctx.strokeStyle = `rgba(255, 230, 150, ${(0.58 + fogIntensity * 0.3) * weight})`
      ctx.lineWidth = Math.max(0.8, rx * 0.0055)
      ctx.setLineDash([rx * 0.032, rx * 0.018, rx * 0.008, rx * 0.018])
      ctx.lineDashOffset = -time * rx * 0.08
      ctx.beginPath()
      ctx.ellipse(0, 0, rx * 0.965, ry * 0.94, 0, startAng, endAng)
      ctx.stroke()
      ctx.setLineDash([])

      // Eclipsed obsidian moons along the orbit
      const moonAngles = [
        0.24 * Math.PI + Math.sin(time * 0.22) * 0.08,
        0.82 * Math.PI + Math.cos(time * 0.18) * 0.08,
        1.18 * Math.PI + Math.sin(time * 0.2) * 0.06,
        1.78 * Math.PI + Math.cos(time * 0.25) * 0.06,
      ]
      moonAngles.forEach((mAng, idx) => {
        const normAng = ((mAng % TAU) + TAU) % TAU
        const inFront = normAng >= 0 && normAng <= Math.PI
        if (inFront !== isFrontPass) return

        const mx = Math.cos(normAng) * rx
        const my = Math.sin(normAng) * ry
        const mR = rx * (idx % 2 === 0 ? 0.062 : 0.042) * weight

        // Golden-crimson corona around the dark moon
        const moonHalo = ctx.createRadialGradient(mx, my, mR * 0.4, mx, my, mR * 2.1)
        moonHalo.addColorStop(0, `rgba(255, 200, 95, ${0.65 * weight})`)
        moonHalo.addColorStop(0.5, `rgba(220, 20, 60, ${0.32 * weight})`)
        moonHalo.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.fillStyle = moonHalo
        ctx.beginPath()
        ctx.arc(mx, my, mR * 2.1, 0, TAU)
        ctx.fill()

        // Pitch-dark obsidian sphere body
        const moonBody = ctx.createRadialGradient(mx - mR * 0.25, my - mR * 0.25, mR * 0.1, mx, my, mR)
        moonBody.addColorStop(0, '#1f080d')
        moonBody.addColorStop(0.7, '#090204')
        moonBody.addColorStop(1, '#030001')
        ctx.fillStyle = moonBody
        ctx.beginPath()
        ctx.arc(mx, my, mR, 0, TAU)
        ctx.fill()

        // Blazing golden crescent rim-light facing the central eye
        const toCenterAng = Math.atan2(-my, -mx)
        ctx.strokeStyle = `rgba(255, 224, 130, ${0.92 * weight})`
        ctx.lineWidth = Math.max(1.2, mR * 0.18)
        ctx.beginPath()
        ctx.arc(mx, my, mR * 0.94, toCenterAng - 1.15, toCenterAng + 1.15)
        ctx.stroke()

        // Star spark on the rim
        const sx = mx + Math.cos(toCenterAng) * mR
        const sy = my + Math.sin(toCenterAng) * mR
        ctx.fillStyle = `rgba(255, 250, 220, ${0.95 * weight})`
        ctx.beginPath()
        ctx.arc(sx, sy, Math.max(1.2, mR * 0.22), 0, TAU)
        ctx.fill()
      })

      ctx.restore()
    }

    const draw = () => {
      const dt = 0.016 * gsap.ticker.deltaRatio()
      const w3 = s.tier3
      const w5 = s.tier5
      const elevated = Math.max(w3 * 0.65, w5)
      const tierSpeedMult = 1 + w3 * 0.2 + w5 * 0.42
      t += (reduced ? 0.12 : 1) * s.speed * tierSpeedMult * dt
      idleClock += dt

      // Gentle autonomous cosmic gaze drift when idle and pointer hasn't moved for 3.5s
      if (track && !reduced && s.mode === 'idle' && performance.now() - lastPointerMoveAt > 3500) {
        lookX(Math.sin(idleClock * 0.55) * 0.22 + Math.cos(idleClock * 0.23) * 0.12)
        lookY(Math.cos(idleClock * 0.42) * 0.15)
      }

      const w = canvas.width
      const h = canvas.height
      const cx = w / 2
      const cy = h / 2
      const R = Math.min(w, h) / 2

      // Living heartbeat breath in idle & sleep
      const idleHeartbeat =
        s.mode === 'idle'
          ? 0.08 * Math.sin(idleClock * 2.1) + 0.04 * Math.pow(Math.max(0, Math.sin(idleClock * 2.1)), 6)
          : s.mode === 'sleep'
            ? 0.1 * Math.sin(idleClock * 1.3)
            : 0

      const fog = Math.min(1.35, s.fog + s.flare * 0.35 + (s.mode === 'listening' ? 0.15 * Math.sin(t * 5) : 0))
      const glow = Math.min(
        1.75,
        s.glow + s.flare * 0.48 + s.tierFlare * 0.45 + w3 * 0.12 + w5 * 0.28 + idleHeartbeat
      )

      ctx.clearRect(0, 0, w, h)

      // ============================================================================
      // 1. COSMIC NEBULA & VOLUMETRIC FOG LIGHT (Reacts strongly to Space / Mic hold)
      // ============================================================================
      const baseHalo = ctx.createRadialGradient(cx, cy, R * 0.12, cx, cy, R * 0.99)
      baseHalo.addColorStop(0, `rgba(255, 195, 90, ${(0.18 + fog * 0.28) * (0.45 + elevated * 0.55)})`)
      baseHalo.addColorStop(0.32, `rgba(235, 20, 55, ${0.26 * glow + fog * 0.26})`)
      baseHalo.addColorStop(0.68, `rgba(120, 6, 24, ${0.18 * glow + fog * 0.2})`)
      baseHalo.addColorStop(1, 'rgba(0, 0, 0, 0)')
      ctx.fillStyle = baseHalo
      ctx.fillRect(0, 0, w, h)

      // Swirling Crimson Nebula Clouds (billow outward when holding Space/Mic)
      ctx.save()
      ctx.globalCompositeOperation = 'screen'
      for (let i = 0; i < NEBULA_CLOUDS.length; i++) {
        const nc = NEBULA_CLOUDS[i]
        const ang = nc.baseAngle + t * nc.speed
        const pulse = 1 + 0.14 * Math.sin(t * 1.4 + nc.phase) + fog * 0.18
        const dist = R * nc.dist * (0.92 + fog * 0.14)
        const nx = cx + Math.cos(ang) * dist
        const ny = cy + Math.sin(ang) * dist * 0.82
        const nr = R * nc.radius * pulse
        const cloudGrad = ctx.createRadialGradient(nx, ny, 0, nx, ny, nr)
        const alpha = (0.09 + fog * 0.24) * (i % 3 === 0 ? 1.15 : 0.85)
        if (i % 4 === 0 && elevated > 0.2) {
          cloudGrad.addColorStop(0, `rgba(255, 175, 70, ${alpha * 0.75})`)
          cloudGrad.addColorStop(0.45, `rgba(220, 18, 50, ${alpha * 0.65})`)
        } else {
          cloudGrad.addColorStop(0, `rgba(255, 32, 68, ${alpha})`)
          cloudGrad.addColorStop(0.55, `rgba(135, 8, 28, ${alpha * 0.55})`)
        }
        cloudGrad.addColorStop(1, 'rgba(0, 0, 0, 0)')
        ctx.fillStyle = cloudGrad
        ctx.beginPath()
        ctx.arc(nx, ny, nr, 0, TAU)
        ctx.fill()
      }

      // Volumetric Fog-Light Cones (Ignite when holding Space or Mic button!)
      if (fog > 0.28) {
        const beamIntensity = Math.min(1, (fog - 0.24) / 0.76)
        const beamCount = 10
        for (let b = 0; b < beamCount; b++) {
          const bAng = (b / beamCount) * TAU + t * (b % 2 === 0 ? 0.18 : -0.14)
          const spread = 0.16 + 0.06 * Math.sin(t * 2.2 + b)
          const reach = R * (0.78 + beamIntensity * 0.22)
          const beamGrad = ctx.createRadialGradient(cx, cy, R * 0.12, cx, cy, reach)
          beamGrad.addColorStop(0, `rgba(255, 225, 145, ${0.22 * beamIntensity})`)
          beamGrad.addColorStop(0.42, `rgba(255, 38, 75, ${0.18 * beamIntensity})`)
          beamGrad.addColorStop(0.8, `rgba(150, 10, 30, ${0.08 * beamIntensity})`)
          beamGrad.addColorStop(1, 'rgba(0, 0, 0, 0)')

          ctx.fillStyle = beamGrad
          ctx.beginPath()
          ctx.moveTo(cx, cy)
          ctx.arc(cx, cy, reach, bAng - spread, bAng + spread)
          ctx.closePath()
          ctx.fill()
        }
      }

      // Floating Cosmic Ember & Gold Dust Motes
      for (let i = 0; i < EMBER_MOTES.length; i++) {
        const m = EMBER_MOTES[i]
        const mAng = m.angle + idleClock * m.drift * (1 + fog * 1.4)
        const radialCycle = (m.dist + idleClock * m.speed * (0.35 + fog * 0.9)) % 0.96
        const mr = R * (0.28 + radialCycle * 0.68)
        const mx = cx + Math.cos(mAng) * mr
        const my = cy + Math.sin(mAng) * mr * 0.86
        const mSize = Math.max(1, R * m.size * (1 + fog * 0.85))
        const twinkle = 0.4 + 0.6 * Math.abs(Math.sin(idleClock * 2.6 + i))
        const mAlpha = twinkle * (0.32 + fog * 0.58)
        ctx.fillStyle = m.isGold
          ? `rgba(255, 215, 115, ${mAlpha})`
          : `rgba(255, 65, 95, ${mAlpha})`
        ctx.beginPath()
        ctx.arc(mx, my, mSize, 0, TAU)
        ctx.fill()
      }
      ctx.restore()

      // ============================================================================
      // 2. TILTED GOLDEN ELLIPTICAL PLANETARY ORBITS (BACK PASS)
      // ============================================================================
      const orbitWeight = Math.max(0.45, elevated)
      drawPlanetaryOrbit(cx, cy, R * 0.93, R * 0.34, -0.35, false, orbitWeight, t, fog)
      drawPlanetaryOrbit(cx, cy, R * 0.86, R * 0.28, 0.24, false, orbitWeight * 0.85, -t * 0.8, fog)

      // ============================================================================
      // 3. CONCENTRIC OBSIDIAN & GILDED ASTROLABE RINGS + ARCANE RUNES
      // ============================================================================
      const rOuterBand = R * 0.66
      const rInnerBand = R * 0.54
      const rRuneMid = (rOuterBand + rInnerBand) * 0.5

      // Dark obsidian metallic astrolabe ring body
      ctx.save()
      const bandGrad = ctx.createRadialGradient(cx, cy, rInnerBand * 0.88, cx, cy, rOuterBand * 1.04)
      bandGrad.addColorStop(0, 'rgba(10, 2, 4, 0.88)')
      bandGrad.addColorStop(0.5, 'rgba(26, 5, 10, 0.94)')
      bandGrad.addColorStop(0.88, 'rgba(48, 8, 16, 0.92)')
      bandGrad.addColorStop(1, 'rgba(12, 2, 5, 0.85)')
      ctx.fillStyle = bandGrad
      ctx.beginPath()
      ctx.arc(cx, cy, rOuterBand, 0, TAU)
      ctx.arc(cx, cy, rInnerBand * 0.86, 0, TAU, true)
      ctx.fill()

      // Outer & Middle Gilded-Crimson Astrolabe Borders
      const goldPrimary = w5 > 0.3 ? '255, 209, 102' : w3 > 0.3 ? '232, 163, 61' : '255, 145, 90'
      ctx.strokeStyle = `rgba(${goldPrimary}, ${0.72 + fog * 0.25})`
      ctx.lineWidth = Math.max(1.2, R * 0.0075)
      ctx.beginPath()
      ctx.arc(cx, cy, rOuterBand, 0, TAU)
      ctx.stroke()

      ctx.strokeStyle = `rgba(255, 38, 70, ${0.58 + fog * 0.32})`
      ctx.lineWidth = Math.max(1, R * 0.005)
      ctx.beginPath()
      ctx.arc(cx, cy, rInnerBand, 0, TAU)
      ctx.stroke()

      // Glowing Arcane Runes around the Outer Astrolabe Band
      const runeCount = 24
      const runeSize = (rOuterBand - rInnerBand) * 0.32
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(t * 0.14)
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.lineWidth = Math.max(1, R * 0.0048)
      ctx.shadowColor = '#ff2a4b'
      ctx.shadowBlur = R * (0.025 + fog * 0.035)
      for (let i = 0; i < runeCount; i++) {
        const rAng = (i / runeCount) * TAU
        // Preserve the original spacing of the ring glyphs
        const modQuad = Math.min(
          Math.abs(rAng % (Math.PI / 2)),
          Math.PI / 2 - Math.abs(rAng % (Math.PI / 2))
        )
        if (modQuad < 0.12) continue

        const shimmer = 0.55 + 0.45 * Math.sin(t * 2.4 + i * 1.3)
        ctx.strokeStyle =
          i % 3 === 0
            ? `rgba(255, 212, 115, ${(0.65 + fog * 0.35) * shimmer})`
            : `rgba(255, 58, 86, ${(0.7 + fog * 0.3) * shimmer})`

        ctx.save()
        ctx.rotate(rAng)
        ctx.translate(0, -rRuneMid)
        const glyph = RUNE_GLYPHS[i % RUNE_GLYPHS.length]
        ctx.beginPath()
        for (let seg = 0; seg < glyph.length; seg++) {
          const [x1, y1, x2, y2] = glyph[seg]
          ctx.moveTo(x1 * runeSize, y1 * runeSize)
          ctx.lineTo(x2 * runeSize, y2 * runeSize)
        }
        ctx.stroke()
        ctx.restore()
      }
      ctx.restore()

      // Inner Counter-Rotating Rune / Telemetry Track
      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(-t * 0.24)
      ctx.strokeStyle = `rgba(${goldPrimary}, ${0.52 + fog * 0.3})`
      ctx.lineWidth = Math.max(1, R * 0.0045)
      ctx.setLineDash([R * 0.022, R * 0.014, R * 0.006, R * 0.014])
      ctx.beginPath()
      ctx.arc(0, 0, rInnerBand * 0.92, 0, TAU)
      ctx.stroke()
      ctx.restore()
      ctx.restore()

      // ============================================================================
      // 4. REACTIVE CORONA WAVEFORM SPIKES (Voice & Mode Energy)
      // ============================================================================
      const scanAt = (t * 2.6) % TAU
      const dimSpikes = new Path2D()
      const hotSpikes = new Path2D()
      const tierAmpBoost = 1 + w3 * 0.18 + w5 * 0.35 + s.tierFlare * 0.4 + fog * 0.25
      for (let i = 0; i < SPIKES; i++) {
        const a = (i / SPIKES) * TAU - Math.PI / 2
        let v =
          Math.sin(a * 3 + t * 1.7) * 0.48 +
          Math.sin(a * 7 - t * 1.1) * 0.3 +
          Math.sin(a * 17 + t * 2.9) * 0.22 +
          Math.sin(a * 23 - t * 4.1) * 0.16
        v = ((v + 1) / 2) ** 2
        if (s.mode === 'listening' && !reduced) v += Math.random() * 0.42
        if (s.mode === 'speaking') v *= 0.55 + 0.45 * Math.abs(Math.sin(t * 7 + a))
        if (s.mode === 'thinking') {
          let d = Math.abs(((a + Math.PI / 2) % TAU) - scanAt)
          d = Math.min(d, TAU - d)
          v += 1.45 * Math.exp(-(d * d) / 0.06)
        }
        const energy = v * s.amp * tierAmpBoost
        const len = R * 0.01 + energy * R * 0.19
        const cos = Math.cos(a)
        const sin = Math.sin(a)
        const path = energy > 0.28 ? hotSpikes : dimSpikes
        path.moveTo(cx + cos * (rOuterBand - len * 0.18), cy + sin * (rOuterBand - len * 0.18))
        path.lineTo(cx + cos * (rOuterBand + len), cy + sin * (rOuterBand + len))
      }
      ctx.save()
      ctx.lineCap = 'round'
      ctx.lineWidth = Math.max(1, R * 0.0062)
      ctx.strokeStyle = `rgba(255, 48, 78, ${0.38 + 0.32 * glow})`
      ctx.stroke(dimSpikes)
      ctx.shadowColor = '#ffd166'
      ctx.shadowBlur = R * (0.045 + fog * 0.04)
      ctx.strokeStyle = '#ffe082'
      ctx.stroke(hotSpikes)
      ctx.restore()

      // ============================================================================
      // 5. ALMOND EYELID FILIGREE SOCKET (Upper & Lower Gilded Cat-Eye Arches)
      // ============================================================================
      const rS = R * 0.35 * (1 + idleHeartbeat * 0.22 + s.flare * 0.035)
      const almondW = R * 0.58
      const almondH = rS * 1.06

      ctx.save()
      ctx.strokeStyle = `rgba(${goldPrimary}, ${0.78 + fog * 0.22})`
      ctx.lineWidth = Math.max(1.4, R * 0.0085)
      ctx.shadowColor = '#ff2a4b'
      ctx.shadowBlur = R * 0.035
      // Upper & lower almond filigree curves meeting toward the E/W lances
      ctx.beginPath()
      ctx.moveTo(cx - almondW, cy)
      ctx.quadraticCurveTo(cx, cy - almondH * 1.42, cx + almondW, cy)
      ctx.quadraticCurveTo(cx, cy + almondH * 1.42, cx - almondW, cy)
      ctx.stroke()

      // Secondary inner gilded eyelid crease
      ctx.strokeStyle = `rgba(255, 70, 95, ${0.62 + fog * 0.28})`
      ctx.lineWidth = Math.max(1, R * 0.005)
      ctx.beginPath()
      ctx.moveTo(cx - almondW * 0.88, cy)
      ctx.quadraticCurveTo(cx, cy - almondH * 1.18, cx + almondW * 0.88, cy)
      ctx.quadraticCurveTo(cx, cy + almondH * 1.18, cx - almondW * 0.88, cy)
      ctx.stroke()
      ctx.restore()

      // ============================================================================
      // 6. THE ABYSSAL EYEBALL & VASCULAR CRIMSON IRIS FILAMENTS
      // ============================================================================
      ctx.save()
      ctx.shadowColor = `rgba(255, 30, 65, ${0.85 * Math.min(1.3, glow)})`
      ctx.shadowBlur = R * (0.14 + fog * 0.08)

      // Deep dark-crimson obsidian eyeball sphere
      const px = cx + s.lookX * rS * 0.22
      const py = cy + s.lookY * rS * 0.15
      const eyeSphere = ctx.createRadialGradient(px, py, rS * 0.04, cx, cy, rS)
      eyeSphere.addColorStop(0, '#8a081c')
      eyeSphere.addColorStop(0.28, '#540410')
      eyeSphere.addColorStop(0.68, '#240106')
      eyeSphere.addColorStop(0.92, '#0b0002')
      eyeSphere.addColorStop(1, '#030001')

      ctx.fillStyle = eyeSphere
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.fill()
      ctx.restore()

      // Clip inside the eyeball sphere for iris filaments, slit pupil, wet reflection & blink
      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.clip()

      // Fiery arterial glow radiating from the pupil center
      const irisCoreGlow = ctx.createRadialGradient(px, py, rS * 0.02, px, py, rS * 0.88)
      irisCoreGlow.addColorStop(0, `rgba(255, 90, 60, ${0.52 + fog * 0.35})`)
      irisCoreGlow.addColorStop(0.38, `rgba(235, 16, 48, ${0.42 + fog * 0.25})`)
      irisCoreGlow.addColorStop(0.78, 'rgba(90, 4, 16, 0.2)')
      irisCoreGlow.addColorStop(1, 'rgba(0, 0, 0, 0)')
      ctx.fillStyle = irisCoreGlow
      ctx.fillRect(cx - rS, cy - rS, rS * 2, rS * 2)

      // Intricate branching crimson vascular iris filaments (matching Crimson Cosmic Eye Sigil.png)
      ctx.save()
      ctx.lineCap = 'round'
      for (let i = 0; i < IRIS_FIBERS.length; i++) {
        const fb = IRIS_FIBERS[i]
        const baseA = fb.angle + Math.sin(t * 0.45 + fb.phase) * 0.025
        const innerR = rS * 0.1
        const outerR = rS * 0.96
        const midR1 = rS * 0.38
        const midR2 = rS * 0.68
        const wave1 = Math.sin(t * 1.6 + fb.phase) * fb.wobble
        const wave2 = Math.cos(t * 1.3 + fb.phase * 1.4) * fb.wobble * 1.2

        const x0 = px + Math.cos(baseA) * innerR * 0.45
        const y0 = py + Math.sin(baseA) * innerR * 0.85
        const x1 = px + Math.cos(baseA + wave1) * midR1
        const y1 = py + Math.sin(baseA + wave1) * midR1
        const x2 = cx + Math.cos(baseA + wave2) * midR2
        const y2 = cy + Math.sin(baseA + wave2) * midR2
        const x3 = cx + Math.cos(baseA) * outerR
        const y3 = cy + Math.sin(baseA) * outerR

        const fiberPulse = 0.58 + 0.42 * Math.sin(t * 2.1 + fb.phase)
        ctx.strokeStyle =
          i % 3 === 0
            ? `rgba(255, 85, 95, ${(0.52 + fog * 0.38) * fiberPulse})`
            : `rgba(220, 18, 46, ${(0.48 + fog * 0.32) * fiberPulse})`
        ctx.lineWidth = Math.max(0.8, rS * 0.014 * fb.thickness)

        ctx.beginPath()
        ctx.moveTo(x0, y0)
        ctx.bezierCurveTo(x1, y1, x2, y2, x3, y3)
        ctx.stroke()

        // Y-branching capillary vessels toward the outer iris
        if (fb.hasBranch) {
          const bAng = baseA + fb.branchDir * (0.11 + wave1 * 0.5)
          const bxEnd = cx + Math.cos(bAng) * (outerR * 0.94)
          const byEnd = cy + Math.sin(bAng) * (outerR * 0.94)
          ctx.lineWidth = Math.max(0.6, rS * 0.009 * fb.thickness)
          ctx.beginPath()
          ctx.moveTo(x1, y1)
          ctx.quadraticCurveTo(x2, y2, bxEnd, byEnd)
          ctx.stroke()
        }
      }
      ctx.restore()

      // Dark vignette ring inside the outer eyeball edge for deep 3D spherical curvature
      const irisVignette = ctx.createRadialGradient(cx, cy, rS * 0.58, cx, cy, rS)
      irisVignette.addColorStop(0, 'rgba(0, 0, 0, 0)')
      irisVignette.addColorStop(0.75, 'rgba(12, 1, 3, 0.48)')
      irisVignette.addColorStop(1, 'rgba(4, 0, 1, 0.92)')
      ctx.fillStyle = irisVignette
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.fill()

      // ============================================================================
      // 7. BLAZING VERTICAL CAT-SLIT PUPIL & WET GLASS CORNEA HIGHLIGHT
      // ============================================================================
      const ph = rS * 0.84
      const pw = rS * Math.max(0.032, s.pupil + idleHeartbeat * 0.18 + s.tierFlare * 0.08) * 1.65

      // Intense fiery crimson-gold corona surrounding the slit pupil
      ctx.save()
      const slitCorona = ctx.createRadialGradient(px, py, pw * 0.2, px, py, ph * 0.95)
      slitCorona.addColorStop(0, `rgba(255, 210, 120, ${0.42 + fog * 0.35})`)
      slitCorona.addColorStop(0.35, `rgba(255, 30, 58, ${0.45 + fog * 0.3})`)
      slitCorona.addColorStop(1, 'rgba(0, 0, 0, 0)')
      ctx.fillStyle = slitCorona
      ctx.beginPath()
      ctx.ellipse(px, py, pw * 3.4, ph * 0.98, 0, 0, TAU)
      ctx.fill()

      // Pitch-black abyssal slit pupil core
      ctx.shadowColor = '#ff2244'
      ctx.shadowBlur = rS * (0.18 + fog * 0.12)
      ctx.fillStyle = '#030001'
      ctx.beginPath()
      ctx.moveTo(px, py - ph)
      ctx.quadraticCurveTo(px + pw, py, px, py + ph)
      ctx.quadraticCurveTo(px - pw, py, px, py - ph)
      ctx.closePath()
      ctx.fill()

      // Outer molten crimson-orange slit rim
      ctx.strokeStyle = `rgba(255, 65, 55, ${0.9 + fog * 0.1})`
      ctx.lineWidth = Math.max(1.6, rS * 0.028)
      ctx.stroke()

      // Inner white-hot golden incandescent slit rim
      const pupilRimGrad = ctx.createLinearGradient(px, py - ph, px, py + ph)
      pupilRimGrad.addColorStop(0, '#ff5466')
      pupilRimGrad.addColorStop(0.25, '#ffd166')
      pupilRimGrad.addColorStop(0.5, '#fff8d6')
      pupilRimGrad.addColorStop(0.75, '#ffd166')
      pupilRimGrad.addColorStop(1, '#ff5466')
      ctx.shadowColor = '#ffd166'
      ctx.shadowBlur = rS * 0.1
      ctx.strokeStyle = pupilRimGrad
      ctx.lineWidth = Math.max(1, rS * 0.015)
      ctx.stroke()
      ctx.restore()

      // Signature 3-pane curved wet glass cornea highlight (Upper-Right, matching reference image)
      ctx.save()
      ctx.translate(cx + rS * 0.36, cy - rS * 0.34)
      ctx.rotate(0.62)
      const panes = [
        { x: -rS * 0.13, w: rS * 0.075, h: rS * 0.048, a: 0.42 },
        { x: -rS * 0.02, w: rS * 0.11, h: rS * 0.056, a: 0.62 },
        { x: rS * 0.11, w: rS * 0.065, h: rS * 0.044, a: 0.36 },
      ]
      panes.forEach((p) => {
        const hlGrad = ctx.createLinearGradient(p.x, -p.h, p.x, p.h)
        hlGrad.addColorStop(0, `rgba(255, 250, 245, ${p.a})`)
        hlGrad.addColorStop(1, 'rgba(255, 200, 205, 0.04)')
        ctx.fillStyle = hlGrad
        ctx.beginPath()
        ctx.roundRect(p.x - p.w / 2, -p.h / 2, p.w, p.h, rS * 0.012)
        ctx.fill()
      })
      ctx.restore()

      // Eyelids for smooth natural blink & sleep standby
      if (s.lid > 0.01) {
        ctx.fillStyle = '#090103'
        ctx.fillRect(cx - rS, cy - rS, rS * 2, rS * s.lid)
        ctx.fillRect(cx - rS, cy + rS - rS * s.lid, rS * 2, rS * s.lid)
        // Golden eyelid rim line when closing
        ctx.strokeStyle = `rgba(${goldPrimary}, ${0.65 * s.lid})`
        ctx.lineWidth = Math.max(1, rS * 0.018)
        ctx.beginPath()
        ctx.moveTo(cx - rS, cy - rS + rS * s.lid)
        ctx.lineTo(cx + rS, cy - rS + rS * s.lid)
        ctx.moveTo(cx - rS, cy + rS - rS * s.lid)
        ctx.lineTo(cx + rS, cy + rS - rS * s.lid)
        ctx.stroke()
      }
      ctx.restore()

      // Sculpted golden-crimson circular iris bezel ring
      ctx.save()
      ctx.strokeStyle = `rgba(${goldPrimary}, ${0.76 + fog * 0.22})`
      ctx.lineWidth = Math.max(1.2, R * 0.008)
      ctx.beginPath()
      ctx.arc(cx, cy, rS, 0, TAU)
      ctx.stroke()
      ctx.restore()

      // ============================================================================
      // 8. TILTED GOLDEN ELLIPTICAL PLANETARY ORBITS (FRONT PASS — 3D OVERLAP)
      // ============================================================================
      drawPlanetaryOrbit(cx, cy, R * 0.93, R * 0.34, -0.35, true, orbitWeight, t, fog)
      drawPlanetaryOrbit(cx, cy, R * 0.86, R * 0.28, 0.24, true, orbitWeight * 0.85, -t * 0.8, fog)


    }

    gsap.ticker.add(draw)
    return () => {
      gsap.ticker.remove(draw)
      blinkCall?.kill()
      ro.disconnect()
      window.removeEventListener('pointermove', onMove)
    }
  }, [track])

  return (
    <canvas
      ref={canvasRef}
      className={`block h-full w-full ${className}`}
      role="img"
      aria-label={`Nightmare is ${mode} (Clearance Level 5)`}
    />
  )
}
