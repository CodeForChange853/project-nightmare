import { useEffect, useRef } from 'react'
import gsap from 'gsap'

/** Two slow pools of red light over a faint dot grid, a vignette, and film grain. */
export default function Background() {
  const left = useRef(null)
  const right = useRef(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tweens = [
      gsap.to(left.current, { xPercent: 6, yPercent: -5, opacity: 0.75, duration: 9, ease: 'sine.inOut', yoyo: true, repeat: -1 }),
      gsap.to(right.current, { xPercent: -5, yPercent: 7, opacity: 0.5, duration: 12, ease: 'sine.inOut', yoyo: true, repeat: -1 }),
    ]
    return () => tweens.forEach((t) => t.kill())
  }, [])

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-abyss">
      <div
        ref={left}
        className="absolute -left-[15%] top-[10%] h-[80vh] w-[70vw] opacity-100"
        style={{ background: 'radial-gradient(closest-side, rgba(220,20,60,0.16), transparent)' }}
      />
      <div
        ref={right}
        className="absolute -right-[10%] -top-[20%] h-[70vh] w-[50vw] opacity-80"
        style={{ background: 'radial-gradient(closest-side, rgba(150,10,35,0.22), transparent)' }}
      />
      <div
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage: 'radial-gradient(rgba(255,84,102,0.16) 1px, transparent 1.2px)',
          backgroundSize: '26px 26px',
          maskImage: 'radial-gradient(ellipse 70% 60% at 35% 50%, #000 10%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 35% 50%, #000 10%, transparent 75%)',
        }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.75)_100%)]" />
      <div className="grain absolute inset-0" />
    </div>
  )
}
