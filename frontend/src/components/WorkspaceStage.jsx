import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import EyeButton from './EyeButton'
import Icon from './Icon'

export default function WorkspaceStage({ categories, browseKey, selectedId, selectedItem, onSelect, onActivate,
  mode, title, caption, canTalk, onPressStart, onPressEnd, onSubmit, readonly, disabled, response, onDismiss, asleep }) {
  const scene = useRef(null)
  const eye = useRef(null)
  const listing = useRef(null)
  const [filter, setFilter] = useState('')
  const [connections, setConnections] = useState([])
  const requestedKey = asleep ? null : browseKey
  const [displayKey, setDisplayKey] = useState(requestedKey)
  const active = categories.find((category) => category.key === displayKey)
  const items = (active?.items ?? []).filter((item) => item.title.toLowerCase().includes(filter.toLowerCase()))
  const expanded = Boolean(active)
  const closing = expanded && !requestedKey

  useEffect(() => {
    if (requestedKey) { setDisplayKey(requestedKey); return }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const timer = setTimeout(() => setDisplayKey(null), reduced ? 0 : 240)
    return () => clearTimeout(timer)
  }, [requestedKey])

  useLayoutEffect(() => { setFilter('') }, [browseKey])
  useLayoutEffect(() => {
    if (!expanded) { setConnections([]); return }
    const root = scene.current
    const list = listing.current
    let frame
    const measure = () => {
      const bounds = root.getBoundingClientRect()
      const orb = eye.current.getBoundingClientRect()
      const viewport = list.getBoundingClientRect()
      const sx = orb.right - bounds.left - orb.width * .08
      const sy = orb.top + orb.height / 2 - bounds.top
      const paths = [...list.querySelectorAll('[data-node]')].flatMap((node) => {
        const box = node.getBoundingClientRect()
        const y = box.top + box.height / 2
        if (y < viewport.top || y > viewport.bottom) return []
        const ex = box.left - bounds.left + 8
        const ey = y - bounds.top
        return [{ id: node.dataset.node, d: `M${sx},${sy} C${sx + (ex - sx) * .5},${sy} ${sx + (ex - sx) * .6},${ey} ${ex},${ey}`, x: ex, y: ey }]
      })
      setConnections(paths)
    }
    // Follow the eye's slide, then measure only on scrolling or resize.
    const until = performance.now() + (window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 850)
    const animate = () => { measure(); if (performance.now() < until) frame = requestAnimationFrame(animate) }
    animate()
    const observer = new ResizeObserver(measure)
    observer.observe(root)
    observer.observe(list)
    list.addEventListener('scroll', measure, { passive: true })
    return () => { cancelAnimationFrame(frame); observer.disconnect(); list.removeEventListener('scroll', measure) }
  }, [expanded, closing, displayKey, filter, active?.items])

  return (
    <section className={`workspace-stage ${expanded && !closing ? 'is-connected' : ''} ${closing ? 'is-closing' : ''}`} aria-label="Workspace">
      <div ref={scene} className="workspace-scene">
        {expanded && <svg className="workspace-connections" aria-hidden="true">
          {connections.map((line, index) => <g key={line.id} className={line.id === selectedId ? 'is-selected' : ''} style={{ '--line-delay': `${index * 30}ms` }}>
            <path d={line.d} pathLength="1" /><circle cx={line.x} cy={line.y} r="2.5" />
          </g>)}
        </svg>}
        <div className="workspace-eye">
          <div ref={eye} className="workspace-eye-art"><EyeButton mode={mode} canTalk={canTalk} onPressStart={onPressStart} onPressEnd={onPressEnd} className="dashboard-eye" /></div>
          <p className="workspace-state" role="status">{title}</p>
          <p className="workspace-caption">{caption}</p>
        </div>
        <div className="workspace-lyrics">{response}</div>
        {expanded && <div className="workspace-browser" key={active.key}>
          <div className="workspace-browser-heading">
            <h1>{active.label}<span className="category-count">{active.items.length}</span></h1>
            <button type="button" className="workspace-dismiss" aria-label="Hide connections" onClick={onDismiss}><Icon name="close" size={16} /></button>
          </div>
          <label className="workspace-filter"><Icon name="search" size={14} /><input aria-label={`Filter ${active.label}`} placeholder="Filter…" value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
          <ul ref={listing} className="workspace-items scroll-thin" aria-label={`Connected ${active.label}`}>
            {items.map((item) => <li key={item.id}>
              <button data-node={item.id} type="button" aria-pressed={item.id === selectedId} onClick={() => onSelect(item)} onDoubleClick={() => !disabled && onActivate(item)} title={item.title}>
                <span className="workspace-node-dot" aria-hidden="true" />
                <span className="min-w-0 flex-1"><span className="workspace-item-title">{item.title}</span>{item.tag && <span className={`workspace-item-tag ${item.tone === 'warn' ? 'text-bile' : ''}`}>{item.tag}</span>}</span>
                <Icon name="chevron" size={14} />
              </button>
            </li>)}
            {items.length === 0 && <li className="p-3 text-sm text-ash">{filter ? 'No matching items.' : active.empty || 'Nothing here yet.'}</li>}
          </ul>
        </div>}
      </div>
      {expanded && !closing && selectedItem && items.some((item) => item.id === selectedId) && <section className="workspace-selection" aria-label="Selected item">
        <div className="min-w-0 flex-1"><span className="text-xs text-ash">{selectedItem.kindLabel}</span><p className="workspace-selection-title">{selectedItem.title}</p></div>
        <div className="flex flex-wrap gap-2">{selectedItem.actions?.filter((action) => !(readonly && action.full)).map((action) => <button type="button" key={action.label} disabled={disabled} onClick={() => onSubmit(action.command)}>{action.label}</button>)}</div>
        <button type="button" aria-label="Close selection" onClick={() => onSelect(null)}><Icon name="close" size={15} /></button>
      </section>}
    </section>
  )
}
