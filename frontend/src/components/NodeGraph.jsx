import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'
import CountUp from './CountUp'
import Icon from './Icon'
import EyeButton from './EyeButton'

gsap.registerPlugin(DrawSVGPlugin, MotionPathPlugin)

const byId = (attr, id) => `[${attr}="${CSS.escape(String(id))}"]`

const THETA_MAX = 1.15 // radians: how far the item arc bends up and down
const SLOT = 42 // px of arc height per visible item
const CHIP_W = 168
const CHIP_H = 58
const CHIP_GAP = 12
const RAIL_W = 44 // room kept on the right for the scroll rail
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function curve(sx, sy, ex, ey, bend = 0.55) {
  const dx = ex - sx
  return `M${sx},${sy} C${sx + dx * bend},${sy} ${sx + dx * (1 - bend)},${ey} ${ex},${ey}`
}

function Meter({ level }) {
  if (level == null) return null
  return (
    <span className="flex gap-[3px]" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`h-[5px] w-[9px] rounded-[1px] ${i < level ? (level === 1 ? 'bg-bile' : 'bg-crimson') : 'bg-vein'}`}
        />
      ))}
    </span>
  )
}

function ItemLabel({ item, selected, clearanceLevel = 1 }) {
  const needsL3 = clearanceLevel < 3 && item.actions?.some((a) => a.full)
  return (
    <>
      <div className="flex items-center justify-between gap-1.5">
        <span className={`block truncate text-[13px] font-medium ${selected ? 'text-white' : 'text-bone/90'}`}>
          {item.title}
        </span>
        {needsL3 && (
          <span
            className="shrink-0 rounded-[3px] border border-amber-500/50 bg-amber-500/10 px-1 py-px font-mono text-[9px] font-semibold text-amber-300"
            title="Requires Level 3 (Operator) to execute"
          >
            L3
          </span>
        )}
      </div>
      <span className="mt-1 flex items-center gap-2">
        {item.tag && (
          <span
            className={`rounded-[4px] border px-1.5 py-px text-[10px] leading-none ${
              item.tone === 'warn'
                ? 'border-bile/40 text-bile'
                : item.tone === 'hot'
                  ? 'border-crimson/50 text-ember'
                  : 'border-scar/70 text-ash'
            }`}
          >
            {item.tag}
          </span>
        )}
        <Meter level={item.meter} />
      </span>
    </>
  )
}

function Chip({ cat, active, onClick, compact = false, style }) {
  return (
    <button
      type="button"
      data-chip={cat.key}
      onClick={onClick}
      aria-pressed={active}
      style={style}
      className={`group flex shrink-0 items-center gap-3 rounded-xl px-3.5 text-left transition-colors ${
        compact ? 'relative h-12' : 'absolute'
      } ${
        active
          ? 'ring-live bg-gradient-to-br from-scar/60 to-clot/90 text-white shadow-[0_0_40px_-8px_rgba(220,20,60,0.6)]'
          : 'tile text-ash hover:text-bone'
      }`}
    >
      <span className={active ? 'text-ember' : 'text-smoke group-hover:text-ash'}>
        <Icon name={cat.icon} size={18} />
      </span>
      <span className="leading-none">
        <CountUp
          value={cat.items.length}
          data-count
          className="inline-block font-display text-[26px] font-bold tracking-wide text-bone"
        />
        <span className="mt-0.5 block text-[11px]">{cat.label}</span>
      </span>
    </button>
  )
}

export default function NodeGraph({
  categories,
  activeKey,
  onCategory,
  selectedId,
  onSelect,
  onActivate,
  mode,
  title,
  caption,
  caption2,
  busy,
  ready,
  onPressStart,
  onPressEnd,
  canTalk,
  focus, // { key, itemId, n }: light up the node (and item) a reply was about
  asleep,
  clearanceLevel = 1,
}) {
  const box = useRef(null)
  const wasAsleep = useRef(false)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [offset, setOffset] = useState(0)
  const scroll = useRef({ value: 0, target: 0 })
  const drag = useRef(null)
  const suppressClick = useRef(false)
  const pendingFocus = useRef(null)
  const lastKey = useRef(null)
  const introDone = useRef(false)

  useLayoutEffect(() => {
    const el = box.current
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width)
      const h = Math.round(entry.contentRect.height)
      setSize((prev) => (prev.w === w && prev.h === h ? prev : { w, h }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const compact = size.w > 0 && (size.w < 720 || size.h < 420)
  const active = categories.find((c) => c.key === activeKey) ?? categories[0]
  const items = active?.items ?? []

  // ---- geometry (desktop) ------------------------------------------------
  const geo = useMemo(() => {
    const { w, h } = size
    if (!w || compact) return null
    const orb = Math.min(h * 0.62, w * 0.34, 440)
    const ox = Math.max(orb / 2 + 8, w * 0.17)
    const oy = h / 2
    const chipX = ox + orb * 0.36 + gsap.utils.clamp(36, 90, w * 0.06)
    const stackH = categories.length * CHIP_H + (categories.length - 1) * CHIP_GAP
    const chips = categories.map((c, i) => ({
      key: c.key,
      x: chipX,
      y: oy - stackH / 2 + i * (CHIP_H + CHIP_GAP),
    }))
    const itemW = 220
    const xBase = chipX + CHIP_W + gsap.utils.clamp(48, 110, w * 0.07)
    const bulge = gsap.utils.clamp(0, 160, w - itemW - RAIL_W - xBase)
    const visible = Math.max(5, Math.floor((h - 40) / SLOT))
    return { orb, ox, oy, chips, xBase, bulge, visible, itemW }
  }, [size, compact, categories])

  // scroll range for the arc
  const range = useMemo(() => {
    const V = geo?.visible ?? 0
    const n = items.length
    if (n <= V - 2) return { min: -(V - n) / 2, max: -(V - n) / 2 }
    return { min: -1, max: n - V + 1 }
  }, [geo, items.length])

  // read through a ref so scrollTo keeps one identity and never re-triggers effects
  const rangeRef = useRef(range)
  rangeRef.current = range

  const scrollTo = useCallback((target, duration = 0.6) => {
    const s = scroll.current
    const { min, max } = rangeRef.current
    s.target = gsap.utils.clamp(min, max, target)
    gsap.to(s, {
      value: s.target,
      duration: reducedMotion() ? 0 : duration,
      ease: 'power3.out',
      overwrite: true,
      onUpdate: () => setOffset(s.value),
    })
  }, [])

  // A new category starts at the top. Anything else that changes the range (a status refresh
  // after a command, a resize, projects added or removed) keeps your place, only clamped.
  useEffect(() => {
    const switched = lastKey.current !== activeKey
    lastKey.current = activeKey
    scrollTo(switched ? range.min : scroll.current.target, 0)
  }, [activeKey, range.min, range.max, scrollTo])

  useEffect(() => {
    const el = box.current
    if (!el || compact) return
    const onWheel = (e) => {
      if (!e.target.closest?.('[data-arc]')) return
      const { min, max } = rangeRef.current
      if (min === max) return
      const px = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY
      const t = scroll.current.target
      // at either end, let the page scroll instead of swallowing the wheel
      if ((px < 0 && t <= min) || (px > 0 && t >= max)) return
      e.preventDefault()
      scrollTo(t + px / 60)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [compact, scrollTo])

  // drag the arc with a mouse, pen or finger; a drag never counts as a click on an item
  const onArcPointerDown = (e) => {
    if (e.button !== 0 || rangeRef.current.min === rangeRef.current.max) return
    drag.current = { y: e.clientY, start: scroll.current.target, id: e.pointerId, moved: false }
  }
  const onArcPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    const dy = e.clientY - d.y
    if (!d.moved) {
      if (Math.abs(dy) < 6) return
      d.moved = true
      e.currentTarget.setPointerCapture(d.id)
    }
    scrollTo(d.start - dy / (SLOT * 0.8), 0.15)
  }
  const onArcPointerUp = () => {
    if (drag.current?.moved) suppressClick.current = true
    drag.current = null
  }
  const onArcClickCapture = (e) => {
    if (!suppressClick.current) return
    suppressClick.current = false
    e.stopPropagation()
    e.preventDefault()
  }
  // keyboard: move focus item by item and bring it to the middle, so focus never
  // lands on an item that has scrolled out (and been unmounted)
  const focusItem = (i, duration) => {
    if (!items.length || !geo) return
    const idx = gsap.utils.clamp(0, items.length - 1, i)
    pendingFocus.current = idx
    scrollTo(idx - (geo.visible - 1) / 2, duration)
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        if (pendingFocus.current !== idx) return // a newer key press wins
        pendingFocus.current = null
        box.current?.querySelector(`[data-index="${idx}"]`)?.focus({ preventScroll: true })
      }),
    )
  }
  const onArcKeyDown = (e) => {
    const page = Math.max(1, (geo?.visible ?? 6) - 3)
    // fast or held keys arrive before focus has moved, so count from the pending target
    const at = pendingFocus.current ?? Number(document.activeElement?.dataset?.index)
    const cur = Number.isFinite(at) ? at : Math.round(scroll.current.target + ((geo?.visible ?? 1) - 1) / 2)
    const next = { ArrowDown: cur + 1, ArrowUp: cur - 1, PageDown: cur + page, PageUp: cur - page, Home: 0, End: items.length - 1 }[
      e.key
    ]
    if (next === undefined) return
    e.preventDefault()
    // adjacent items are always mounted, so arrows can animate; jumps land instantly
    focusItem(next, e.key.startsWith('Arrow') ? 0.35 : 0)
  }

  const place = useCallback(
    (i) => {
      const { visible: V, xBase, bulge, oy } = geo
      const half = (V - 1) / 2
      const u = (i - offset - half) / half
      const th = u * THETA_MAX
      const x = xBase + (bulge * (Math.cos(th) - Math.cos(THETA_MAX))) / (1 - Math.cos(THETA_MAX))
      // even vertical spacing (the curve lives only in x), so rows never overlap at the ends
      const y = oy + (size.h / 2 - 26) * u
      const opacity = gsap.utils.clamp(0, 1, (1.12 - Math.abs(u)) / 0.3)
      return { x, y, opacity, hidden: Math.abs(u) > 1.2 }
    },
    [geo, offset, size.h],
  )

  // ---- motion -------------------------------------------------------------
  // first reveal: orb wakes, lines draw out, nodes arrive
  useLayoutEffect(() => {
    if (!ready || !size.w || introDone.current) return
    introDone.current = true
    if (reducedMotion()) return
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
      tl.from('[data-orb]', { scale: 0.55, opacity: 0, duration: 1.1, ease: 'expo.out' })
        .from('[data-orbtext]', { y: 10, opacity: 0, duration: 0.6, stagger: 0.08 }, 0.35)
        .fromTo('[data-trunk]', { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, stagger: 0.06, clearProps: 'all' }, 0.45)
        .from('[data-chip]', { x: -16, opacity: 0, duration: 0.5, stagger: 0.06 }, 0.7)
    }, box)
    return () => ctx.revert()
  }, [ready, size.w])

  // ---- sleep: fold the web away and let the eye drift to the middle; wake: unfold it again ----
  // No gsap.context here on purpose: reverting would undo the sleep pose on any re-render.
  useLayoutEffect(() => {
    const root = box.current
    if (!root || !size.w) return
    const web = root.querySelector('[data-web]')
    const orbWrap = root.querySelector('[data-orbwrap]')
    const reduced = reducedMotion()
    const d = (s) => (reduced ? 0 : s)
    let tl
    if (asleep) {
      const toCenter = geo && orbWrap ? size.w / 2 - geo.ox : 0
      tl = gsap
        .timeline()
        .to(root.querySelectorAll('[data-web] [data-item]'), { opacity: 0, x: -14, duration: d(0.25), stagger: d(0.012) })
        .to(root.querySelectorAll('[data-web] [data-chip]'), { opacity: 0, x: -28, duration: d(0.3), stagger: d(0.05) }, '<0.1')
        .to(web, { autoAlpha: 0, duration: d(0.4) })
      if (orbWrap) tl.to(orbWrap, { x: toCenter, duration: d(1.3), ease: 'power3.inOut' }, '<')
      // on a phone the page may be scrolled down the list; bring the eye back into view
      else root.scrollIntoView({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })
    } else if (wasAsleep.current) {
      gsap.set(root.querySelectorAll('[data-web] [data-item], [data-web] [data-chip]'), { clearProps: 'opacity,transform' })
      tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
      if (orbWrap) tl.to(orbWrap, { x: 0, duration: d(1), ease: 'power3.inOut' })
      tl.set(web, { autoAlpha: 1 }, d(0.45))
        .fromTo(root.querySelectorAll('[data-trunk]'), { drawSVG: '0%' }, { drawSVG: '100%', duration: d(0.6), stagger: d(0.06), clearProps: 'strokeDasharray,strokeDashoffset' }, '<')
        .from(root.querySelectorAll('[data-web] [data-chip]'), { x: -16, opacity: 0, duration: d(0.45), stagger: d(0.06) }, '<0.2')
        .fromTo(root.querySelectorAll('[data-fan]'), { drawSVG: '0%' }, { drawSVG: '100%', duration: d(0.6), stagger: d(0.02), clearProps: 'strokeDasharray,strokeDashoffset' }, '<0.25')
        .from(root.querySelectorAll('[data-web] [data-item]'), { x: -14, opacity: 0, duration: d(0.4), stagger: d(0.025) }, '<0.15')
    }
    wasAsleep.current = asleep
    return () => tl?.progress(1).kill() // finish, don't revert: the pose must stick
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asleep])

  // ---- focus: a reply was about this node/item. Flash the count, run a spark down the lines ----
  useEffect(() => {
    const root = box.current
    if (!focus || !root || !size.w) return
    const reduced = reducedMotion()
    const idx = focus.itemId ? items.findIndex((i) => i.id === focus.itemId) : -1
    if (idx >= 0 && geo && !compact) scrollTo(idx - (geo.visible - 1) / 2)

    const itemEl = () => root.querySelector(byId('data-item-id', focus.itemId))
    // compact: scroll only the list, never the page (on a phone the reply panel may be in view)
    const list = root.querySelector('[data-compact-list]')
    const el = itemEl()
    if (idx >= 0 && compact && list && el) {
      list.scrollTo({ top: el.offsetTop - (list.clientHeight - el.offsetHeight) / 2, behavior: reduced ? 'auto' : 'smooth' })
    }
    if (reduced) return

    const chip = root.querySelector(byId('data-chip', focus.key))
    const count = chip?.querySelector('[data-count]')
    const trunk = root.querySelector(byId('data-trunk-key', focus.key))
    const spark = root.querySelector('[data-spark]')
    const pulseItem = () => {
      const el = itemEl()
      if (!el) return
      gsap.fromTo(
        el,
        { boxShadow: '0 0 0 0 rgba(255,84,102,0.9)', scale: 1.06 },
        { boxShadow: '0 0 0 16px rgba(255,84,102,0)', scale: 1, duration: 0.9, ease: 'power2.out', clearProps: 'boxShadow,transform' },
      )
    }

    const tl = gsap.timeline()
    const hit = spark && trunk ? 0.5 : 0 // when the spark reaches the node
    if (hit) {
      tl.set(spark, { opacity: 1 }).to(spark, { motionPath: { path: trunk }, duration: 0.5, ease: 'power2.in' })
    }
    if (chip) {
      tl.fromTo(
        chip,
        { boxShadow: '0 0 0 0 rgba(255,84,102,0.85)' },
        { boxShadow: '0 0 0 18px rgba(255,84,102,0)', duration: 1, ease: 'power2.out', clearProps: 'boxShadow' },
        hit,
      )
    }
    if (count) {
      tl.fromTo(
        count,
        { scale: 1.55, color: '#ff5466', textShadow: '0 0 18px rgba(255,84,102,0.9)' },
        { scale: 1, color: '#f1e6e4', textShadow: '0 0 0 rgba(255,84,102,0)', duration: 0.9, ease: 'back.out(3)', clearProps: 'transform,color,textShadow' },
        hit,
      )
    }
    if (idx >= 0 && hit && !compact) {
      // by now the arc has scrolled the item into place, so its fan line exists
      tl.add(() => {
        const fan = root.querySelector(byId('data-fan-id', focus.itemId))
        if (!fan) return gsap.to(spark, { opacity: 0, duration: 0.2 })
        gsap.to(spark, {
          motionPath: { path: fan },
          duration: 0.55,
          ease: 'power2.inOut',
          onComplete: () => {
            gsap.to(spark, { opacity: 0, duration: 0.25 })
            pulseItem()
          },
        })
      }, 0.75)
    } else {
      if (hit) tl.to(spark, { opacity: 0, duration: 0.25 }, hit)
      if (idx >= 0) tl.add(pulseItem, 0.35)
    }
    return () => {
      tl.kill()
      if (spark) gsap.set(spark, { opacity: 0 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.n])

  // fan out again every time a category is chosen
  useLayoutEffect(() => {
    if (!ready || !size.w || reducedMotion()) return
    const ctx = gsap.context(() => {
      gsap.fromTo(
        '[data-fan]',
        { drawSVG: '0%' },
        { drawSVG: '100%', duration: 0.65, ease: 'power2.out', stagger: 0.025, delay: 0.1, clearProps: 'all' },
      )
      gsap.from('[data-item]', { x: -14, opacity: 0, duration: 0.45, ease: 'power2.out', stagger: 0.03, delay: 0.25 })
    }, box)
    return () => ctx.revert()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, ready, compact])

  // ---- clearance surge wave: re-energize the web when clearance changes ----
  const prevClearance = useRef(clearanceLevel)
  useEffect(() => {
    if (!ready || !size.w || reducedMotion() || prevClearance.current === clearanceLevel) {
      prevClearance.current = clearanceLevel
      return
    }
    prevClearance.current = clearanceLevel
    const root = box.current
    if (!root) return
    const trunks = root.querySelectorAll('[data-trunk]')
    const fans = root.querySelectorAll('[data-fan]')
    const chipsEl = root.querySelectorAll('[data-chip]')
    gsap.fromTo(
      trunks,
      { strokeWidth: clearanceLevel === 5 ? 3.5 : clearanceLevel === 3 ? 2.5 : 2, opacity: 1 },
      { strokeWidth: 1, duration: 0.85, ease: 'power2.out', clearProps: 'strokeWidth' }
    )
    gsap.fromTo(
      fans,
      { drawSVG: '0%' },
      { drawSVG: '100%', duration: 0.6, ease: 'power2.out', stagger: 0.02, clearProps: 'strokeDasharray,strokeDashoffset' }
    )
    gsap.fromTo(
      chipsEl,
      { scale: 1.05 },
      { scale: 1, duration: 0.6, stagger: 0.04, ease: 'back.out(2)', clearProps: 'transform' }
    )
  }, [clearanceLevel, ready, size.w])

  const orbButton = (sizeStyle) => (
    <EyeButton
      mode={mode}
      canTalk={canTalk}
      onPressStart={onPressStart}
      onPressEnd={onPressEnd}
      style={sizeStyle}
      clearanceLevel={clearanceLevel}
    />
  )

  const captionBlock = (
    <div className="pointer-events-none text-center" aria-live="polite">
      <p data-orbtext className="text-[13px] font-medium text-bone">
        {caption}
        {mode === 'listening' && <span className="caret ml-0.5 text-ember">â–Œ</span>}
      </p>
      {caption2 && (
        <p data-orbtext className="mx-auto mt-1 max-w-[30ch] truncate text-[11px] text-smoke">
          {caption2}
        </p>
      )}
    </div>
  )

  // ---- compact (phone / narrow) layout --------------------------------------
  if (compact || !geo) {
    return (
      <div ref={box} className="flex h-full min-h-0 flex-col gap-4">
        <div className="flex flex-col items-center gap-2 pt-2">
          {orbButton({ width: 'min(64vw, 240px)', aspectRatio: '1' })}
          <p data-orbtext className="font-display text-[22px] font-bold uppercase leading-none tracking-[0.16em] text-bone">
            {title}
          </p>
          {captionBlock}
        </div>
        <div data-web className="flex flex-col gap-4">
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {categories.map((c) => (
              <Chip key={c.key} cat={c} compact active={c.key === active?.key} onClick={() => onCategory(c.key)} />
            ))}
        </div>
        <ul data-compact-list className="scroll-thin relative flex max-h-[45dvh] flex-col gap-1.5 overflow-y-auto pr-1">
          {items.length === 0 && <li className="px-1 text-[13px] text-smoke">{active?.empty}</li>}
          {items.map((item) => (
            <li key={item.id} data-item data-item-id={item.id} className="rounded-lg">
              <button
                type="button"
                onClick={() => onSelect(item)}
                onDoubleClick={() => onActivate(item)}
                className={`w-full rounded-lg px-3 py-2 text-left ${
                  item.id === selectedId ? 'bg-scar/50 ring-1 ring-crimson/60' : 'tile'
                }`}
              >
                <ItemLabel item={item} selected={item.id === selectedId} clearanceLevel={clearanceLevel} />
              </button>
            </li>
          ))}
        </ul>
        </div>
      </div>
    )
  }

  // ---- desktop arc layout ---------------------------------------------------
  const { orb, ox, oy, chips, itemW } = geo
  const trunkX = ox + orb * 0.31
  const activeChip = chips.find((c) => c.key === active?.key) ?? chips[0]
  const fanX = activeChip.x + CHIP_W
  const fanY = activeChip.y + CHIP_H / 2
  const placed = items.map((item, i) => ({ item, i, ...place(i) })).filter((p) => !p.hidden)
  const scrollable = range.max > range.min
  const first = gsap.utils.clamp(1, items.length, Math.round(offset) + 1)
  const last = gsap.utils.clamp(1, items.length, Math.round(offset) + geo.visible)
  const thumb = Math.min(1, geo.visible / (items.length + 2))
  const progress = scrollable ? (offset - range.min) / (range.max - range.min) : 0

  const isL5 = clearanceLevel === 5
  const isL3 = clearanceLevel === 3
  const activeTrunkStroke = isL5 ? '#ffd166' : isL3 ? '#e8a33d' : '#ff5466'
  const inactiveTrunkStroke = isL5 ? '#6e1d27' : isL3 ? '#58211b' : '#5c1a24'
  const sparkFill = isL5 ? '#fff3c4' : isL3 ? '#ffe4a8' : '#ffd3d8'
  const sparkShadow = isL5 ? 'drop-shadow(0 0 8px #ffd166)' : isL3 ? 'drop-shadow(0 0 6px #e8a33d)' : 'drop-shadow(0 0 6px #ff5466)'

  return (
    <div ref={box} className="relative h-full min-h-0 w-full overflow-hidden">
      {/* the "web": lines, nodes and arc. Sleep folds all of it away; the eye stays. */}
      <div data-web className="absolute inset-0">
        <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" aria-hidden>
          <defs>
            <linearGradient id="fan-stroke" x1="0" x2="1">
              <stop offset="0" stopColor={isL5 ? '#ffd166' : isL3 ? '#ff8a47' : '#ff5466'} stopOpacity="0.9" />
              <stop offset="1" stopColor={isL5 ? '#ff1e42' : isL3 ? '#e8a33d' : '#dc143c'} stopOpacity="0.35" />
            </linearGradient>
          </defs>
          {chips.map((c) => {
            const on = c.key === activeChip.key
            const d = curve(trunkX, oy, c.x, c.y + CHIP_H / 2, 0.5)
            return (
              <g key={c.key}>
                <path
                  data-trunk
                  data-trunk-key={c.key}
                  d={d}
                  fill="none"
                  stroke={on ? activeTrunkStroke : inactiveTrunkStroke}
                  strokeWidth={on ? (isL5 ? 1.8 : 1.5) : 1}
                />
                {(busy || isL5) && (
                  <path
                    d={d}
                    fill="none"
                    stroke={activeTrunkStroke}
                    strokeOpacity={busy ? 0.85 : 0.4}
                    strokeWidth="1.5"
                    className="flow"
                  />
                )}
              </g>
            )
          })}
          {placed.map(({ item, x, y, opacity }) => (
            <g key={item.id} opacity={opacity}>
              <path
                data-fan
                data-fan-id={item.id}
                d={curve(fanX, fanY, x - 8, y)}
                fill="none"
                stroke={item.id === selectedId ? activeTrunkStroke : 'url(#fan-stroke)'}
                strokeOpacity={item.id === selectedId ? 1 : 0.55}
                strokeWidth={item.id === selectedId ? 1.6 : 1}
              />
              <circle
                cx={x - 6}
                cy={y}
                r={item.id === selectedId ? 4 : 2.8}
                fill={item.id === selectedId ? activeTrunkStroke : isL5 ? '#ff4d6d' : isL3 ? '#ff8a47' : '#ff8a95'}
              />
            </g>
          ))}
          <circle cx={fanX} cy={fanY} r="3.5" fill={activeTrunkStroke} />
          {/* travels eye -> node -> item when a reply is about them */}
          <circle data-spark cx="0" cy="0" r="5" fill={sparkFill} opacity="0" style={{ filter: sparkShadow }} />
        </svg>

        {chips.map((c) => {
          const cat = categories.find((k) => k.key === c.key)
          return (
            <Chip
              key={c.key}
              cat={cat}
              active={c.key === activeChip.key}
              onClick={() => onCategory(c.key)}
              style={{ left: c.x, top: c.y, width: CHIP_W, height: CHIP_H }}
            />
          )
        })}

        {/* the arc */}
        <div
          data-arc
          role="group"
          aria-label={`${active?.label}, ${items.length} items`}
          onPointerDown={onArcPointerDown}
          onPointerMove={onArcPointerMove}
          onPointerUp={onArcPointerUp}
          onPointerCancel={onArcPointerUp}
          onClickCapture={onArcClickCapture}
          onKeyDown={onArcKeyDown}
          className={`absolute inset-y-0 right-0 ${scrollable ? 'touch-none' : ''}`}
          style={{ left: fanX + 8 }}
        >
          {items.length === 0 && (
            <p className="absolute max-w-[24ch] text-[13px] text-smoke" style={{ left: geo.xBase - fanX, top: oy - 10 }}>
              {active?.empty}
            </p>
          )}
          {placed.map(({ item, i, x, y, opacity }) => {
            const sel = item.id === selectedId
            return (
              <button
                key={item.id}
                data-item
                data-index={i}
                data-item-id={item.id}
                type="button"
                onClick={() => onSelect(item)}
                onDoubleClick={() => onActivate(item)}
                onFocus={() => {
                  const half = (geo.visible - 1) / 2
                  if (Math.abs(i - scroll.current.target - half) > half * 0.6) scrollTo(i - half)
                }}
                style={{
                  left: x - fanX - 8,
                  top: y - 19,
                  width: itemW,
                  opacity,
                  pointerEvents: opacity < 0.3 ? 'none' : undefined,
                }}
                className={`absolute rounded-lg px-2.5 py-1 text-left transition-[background-color,box-shadow] ${
                  sel
                    ? isL5
                      ? 'bg-scar/55 shadow-[0_0_30px_-4px_rgba(255,209,102,0.45)] ring-1 ring-[#ffd166]/80'
                      : isL3
                        ? 'bg-scar/50 shadow-[0_0_28px_-6px_rgba(232,163,61,0.5)] ring-1 ring-amber-400/80'
                        : 'bg-scar/45 shadow-[0_0_28px_-6px_rgba(220,20,60,0.7)] ring-1 ring-crimson/70'
                    : 'hover:bg-vein/50'
                }`}
              >
                <ItemLabel item={item} selected={sel} clearanceLevel={clearanceLevel} />
              </button>
            )
          })}
          {scrollable && (
            <p className="pointer-events-none absolute bottom-1 text-[11px] text-smoke" style={{ left: geo.xBase - fanX }}>
              {first}â€“{last} of {items.length}. Scroll, drag or use the arrow keys.
            </p>
          )}
        </div>

        {scrollable && (
          <div className="absolute right-2 top-1/2 flex -translate-y-1/2 flex-col items-center gap-2">
            <button
              type="button"
              aria-label="Scroll up"
              onClick={() => scrollTo(scroll.current.target - Math.max(1, geo.visible - 3))}
              disabled={offset <= range.min + 0.01}
              className="grid h-7 w-7 place-items-center rounded-full border border-scar/60 text-ash hover:text-bone disabled:opacity-30"
            >
              <Icon name="chevron" size={14} className="-rotate-90" />
            </button>
            <div
              className="relative h-40 w-[3px] cursor-pointer rounded-full bg-vein"
              onPointerDown={(e) => {
                // jump: clicking the track moves the arc to that spot
                const r = e.currentTarget.getBoundingClientRect()
                const f = gsap.utils.clamp(0, 1, (e.clientY - r.top) / r.height)
                scrollTo(range.min + f * (range.max - range.min))
              }}
              aria-hidden
            >
              <div
                className="absolute left-0 w-full rounded-full bg-ember shadow-[0_0_8px_#ff5466]"
                style={{ height: `${thumb * 100}%`, top: `${progress * (1 - thumb) * 100}%` }}
              />
            </div>
            <button
              type="button"
              aria-label="Scroll down"
              onClick={() => scrollTo(scroll.current.target + Math.max(1, geo.visible - 3))}
              disabled={offset >= range.max - 0.01}
              className="grid h-7 w-7 place-items-center rounded-full border border-scar/60 text-ash hover:text-bone disabled:opacity-30"
            >
              <Icon name="chevron" size={14} className="rotate-90" />
            </button>
          </div>
        )}
      </div>

      {/* the eye with its title, above the web; it drifts to the middle while asleep */}
      <div
        data-orbwrap
        className="absolute flex flex-col items-center"
        style={{ left: ox - orb / 2, top: oy - orb / 2, width: orb }}
      >
        <div className="pointer-events-none absolute -top-12 text-center">
          <p data-orbtext className="font-display text-[26px] font-bold uppercase leading-none tracking-[0.16em] text-bone">
            {title}
          </p>
        </div>
        {orbButton({ width: orb, height: orb })}
        <div className="absolute top-full mt-1 w-[130%]">{captionBlock}</div>
      </div>
    </div>
  )
}
