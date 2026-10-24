import { useLayoutEffect, useRef } from 'react'
import gsap from 'gsap'

const round = (v) => Math.round(v)

/**
 * A number that counts from its last value to the new one (from 0 on first show).
 * The span has no React children on purpose: only this effect writes its text, so a
 * running tween and a React re-render can never fight and leave a stale number behind.
 */
export default function CountUp({ value, format = round, className = '', ...rest }) {
  const el = useRef(null)
  const shown = useRef(0)

  useLayoutEffect(() => {
    const o = { v: shown.current }
    const paint = () => {
      if (el.current) el.current.textContent = format(o.v)
    }
    paint()
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t = gsap.to(o, {
      v: Number(value) || 0,
      duration: reduced ? 0 : 0.9,
      ease: 'power2.out',
      onUpdate: () => {
        shown.current = o.v
        paint()
      },
      onComplete: () => {
        shown.current = o.v
        paint()
      },
    })
    return () => t.kill()
  }, [value, format])

  return <span ref={el} className={className} {...rest} />
}
