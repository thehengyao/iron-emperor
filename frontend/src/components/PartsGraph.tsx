import { useRef, useEffect, useMemo, useCallback } from 'react'

/* ═══ Types ═══ */
interface Part { name: string; price?: number; estimated_price?: number; quantity?: number }
interface Conn { from: string; to: string; type: string }
interface Props { bom: Part[]; connections: Conn[] }

interface GNode {
  id: number; name: string; label: string; price: number
  x: number; y: number; vx: number; vy: number
  r: number; base: number
}
interface GEdge { a: number; b: number }

const W = 820, H = 380

/* ═══ Helpers ═══ */

function shorten(name: string): string {
  const c = name
    .replace(/\b(for|with|and|the|a|an|module|kit|combo|basic|premium|quality|electronic|digital|sensor|board)\b/gi, '')
    .replace(/\s+/g, ' ').trim()
  let out = ''
  for (const w of c.split(' ')) {
    if ((out + ' ' + w).trim().length > 16) break
    out = (out + ' ' + w).trim()
  }
  return out || name.slice(0, 14)
}

function matchComp(connPart: string, bomName: string): boolean {
  const comp = connPart.split('.')[0].replace(/_/g, ' ').toLowerCase()
  const name = bomName.toLowerCase()
  if (name.includes(comp)) return true
  const first = comp.split(' ')[0]
  return first.length >= 3 && name.includes(first)
}

function buildGraph(bom: Part[], connections: Conn[]): { nodes: GNode[]; edges: GEdge[] } {
  const maxP = Math.max(1, ...bom.map(p => p.price || p.estimated_price || 100))
  const nodes: GNode[] = bom.map((p, i) => {
    const a = (i / bom.length) * Math.PI * 2 + (Math.random() - 0.5) * 0.4
    const d = 90 + Math.random() * 70
    const price = p.price || p.estimated_price || 100
    const r = 3 + (Math.log(price + 1) / Math.log(maxP + 1)) * 10
    return {
      id: i, name: p.name, label: shorten(p.name), price,
      x: W / 2 + Math.cos(a) * d, y: H / 2 + Math.sin(a) * d,
      vx: (Math.random() - 0.5) * 1.5, vy: (Math.random() - 0.5) * 1.5,
      r, base: 0.35 + (price / maxP) * 0.55,
    }
  })

  const seen = new Set<string>()
  const edges: GEdge[] = []
  for (const c of connections) {
    let ai = -1, bi = -1
    for (let i = 0; i < bom.length; i++) {
      if (ai < 0 && matchComp(c.from, bom[i].name)) ai = i
      if (bi < 0 && matchComp(c.to, bom[i].name)) bi = i
    }
    if (ai >= 0 && bi >= 0 && ai !== bi) {
      const k = `${Math.min(ai, bi)}-${Math.max(ai, bi)}`
      if (!seen.has(k)) { seen.add(k); edges.push({ a: ai, b: bi }) }
    }
  }
  // Fallback: chain neighbors if very few edges
  if (edges.length < 3 && bom.length > 3) {
    for (let i = 0; i < bom.length - 1 && edges.length < bom.length; i++) {
      const k = `${i}-${i + 1}`
      if (!seen.has(k)) { seen.add(k); edges.push({ a: i, b: i + 1 }) }
    }
  }
  return { nodes, edges }
}

/* ═══ Static stars ═══ */
const STARS = Array.from({ length: 140 }, () => ({
  x: Math.random() * W, y: Math.random() * H,
  s: Math.random() * 1.2 + 0.3, a: Math.random() * 0.1 + 0.02,
}))

/* ═══ Component ═══ */

export default function PartsGraph({ bom, connections }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mouseRef = useRef({ x: -999, y: -999 })

  const graph = useMemo(() => buildGraph(bom, connections), [bom, connections])

  useEffect(() => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')!
    const { nodes, edges } = graph
    const cx = W / 2, cy = H / 2
    let animId: number

    const loop = () => {
      /* ── Physics ── */
      for (const n of nodes) {
        // Center gravity
        n.vx += (cx - n.x) * 0.00025
        n.vy += (cy - n.y) * 0.00025
        // Repulsion
        for (const m of nodes) {
          if (m.id === n.id) continue
          const dx = n.x - m.x, dy = n.y - m.y
          const d2 = dx * dx + dy * dy + 1
          const f = 350 / d2
          const d = Math.sqrt(d2)
          n.vx += (dx / d) * f; n.vy += (dy / d) * f
        }
        // Bounds
        if (n.x < 50) n.vx += 0.3
        if (n.x > W - 50) n.vx -= 0.3
        if (n.y < 35) n.vy += 0.3
        if (n.y > H - 35) n.vy -= 0.3
        // Drift
        n.vx += (Math.random() - 0.5) * 0.05
        n.vy += (Math.random() - 0.5) * 0.05
        // Damp + clamp
        n.vx *= 0.97; n.vy *= 0.97
        const mv = 1.3
        n.vx = Math.max(-mv, Math.min(mv, n.vx))
        n.vy = Math.max(-mv, Math.min(mv, n.vy))
        n.x += n.vx; n.y += n.vy
      }
      // Springs
      for (const e of edges) {
        const a = nodes[e.a], b = nodes[e.b]
        const dx = b.x - a.x, dy = b.y - a.y
        const d = Math.sqrt(dx * dx + dy * dy) + 1
        const f = (d - 110) * 0.0006
        const fx = (dx / d) * f, fy = (dy / d) * f
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
      }

      /* ── Render ── */
      ctx.clearRect(0, 0, W, H)

      // Stars
      for (const s of STARS) {
        ctx.fillStyle = `rgba(255,255,255,${s.a})`
        ctx.fillRect(s.x, s.y, s.s, s.s)
      }

      // Hovered node
      const mx = mouseRef.current.x, my = mouseRef.current.y
      let hov: GNode | null = null
      for (const n of nodes) {
        if (Math.hypot(mx - n.x, my - n.y) < n.r + 14) { hov = n; break }
      }

      // Edges
      for (const e of edges) {
        const a = nodes[e.a], b = nodes[e.b]
        const d = Math.hypot(b.x - a.x, b.y - a.y)
        const hi = hov != null && (e.a === hov.id || e.b === hov.id)
        const alpha = hi ? 0.45 : (hov ? 0.03 : Math.max(0.05, 0.22 - d * 0.0007))
        // Curve midpoint
        const cmx = (a.x + b.x) / 2 + (a.y - b.y) * 0.07
        const cmy = (a.y + b.y) / 2 + (b.x - a.x) * 0.07
        // Glow
        ctx.strokeStyle = `rgba(255,255,255,${alpha * 0.25})`
        ctx.lineWidth = 2.5
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(cmx, cmy, b.x, b.y); ctx.stroke()
        // Core
        ctx.strokeStyle = `rgba(255,255,255,${alpha})`
        ctx.lineWidth = 0.5
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(cmx, cmy, b.x, b.y); ctx.stroke()
      }

      // Nodes
      for (const n of nodes) {
        const isH = hov != null && n.id === hov.id
        const isC = hov != null && edges.some(e => (e.a === hov!.id && e.b === n.id) || (e.b === hov!.id && e.a === n.id))
        const br = isH ? 1 : isC ? 0.85 : (hov ? 0.1 : n.base)

        // Glow halo
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 3.5)
        g.addColorStop(0, `rgba(255,255,255,${br * 0.3})`)
        g.addColorStop(1, 'rgba(255,255,255,0)')
        ctx.fillStyle = g
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 3.5, 0, Math.PI * 2); ctx.fill()

        // Core dot
        ctx.fillStyle = `rgba(255,255,255,${br})`
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill()

        // Label
        if (n.r > 5.5 || isH || isC) {
          ctx.fillStyle = `rgba(255,255,255,${isH || isC ? 0.85 : br * 0.45})`
          ctx.font = `${isH ? 10 : 9}px "Space Mono", monospace`
          ctx.fillText(n.label, n.x + n.r + 5, n.y + 3)
        }
      }

      // Tooltip
      if (hov) {
        const txt = `${hov.name.slice(0, 40)}  $${hov.price.toLocaleString('en-US')}`
        ctx.font = '10px "Space Mono", monospace'
        const tw = ctx.measureText(txt).width
        let tx = hov.x + hov.r + 10
        const ty = hov.y - hov.r - 14
        if (tx + tw + 12 > W) tx = hov.x - tw - hov.r - 16
        ctx.fillStyle = 'rgba(3,3,3,0.92)'
        ctx.fillRect(tx - 6, ty - 12, tw + 12, 18)
        ctx.strokeStyle = 'rgba(255,255,255,0.12)'
        ctx.lineWidth = 0.5
        ctx.strokeRect(tx - 6, ty - 12, tw + 12, 18)
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.fillText(txt, tx, ty)
      }

      // Summary bar
      const total = nodes.reduce((s, n) => s + n.price, 0)
      ctx.fillStyle = 'rgba(255,255,255,0.2)'
      ctx.font = '10px "Space Mono", monospace'
      ctx.fillText(`${nodes.length} COMPONENTS · $${total.toLocaleString('en-US')} · ${edges.length} CONNECTIONS`, 12, H - 10)

      animId = requestAnimationFrame(loop)
    }

    loop()
    return () => cancelAnimationFrame(animId)
  }, [graph])

  const onMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = (e.target as HTMLCanvasElement).getBoundingClientRect()
    mouseRef.current = {
      x: (e.clientX - r.left) * (W / r.width),
      y: (e.clientY - r.top) * (H / r.height),
    }
  }, [])

  return (
    <canvas
      ref={canvasRef} width={W} height={H}
      style={{ width: '100%', height: H, display: 'block', cursor: 'crosshair' }}
      onMouseMove={onMove}
      onMouseLeave={() => { mouseRef.current = { x: -999, y: -999 } }}
    />
  )
}
