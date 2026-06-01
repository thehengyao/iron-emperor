import { useState, useCallback, useRef, useEffect } from 'react'
import MatrixPanel from './components/MatrixPanel'
import LiveGraph from './components/LiveGraph'
import PartsGraph from './components/PartsGraph'
import { buildProject, buildProjectStream, getStats } from './lib/api'
import type { BuildResponse, AppState, LogEntry } from './lib/types'

/* ═══════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════ */

const STAGE_DEFS = [
  { id: 'requirements', label: 'REQUIREMENTS', index: '01' },
  { id: 'parts', label: 'PARTS', index: '02' },
  { id: 'pcb', label: 'PCB', index: '03' },
  { id: 'enclosure', label: 'ENCLOSURE', index: '04' },
  { id: 'assembly', label: 'ASSEMBLY', index: '05' },
  { id: 'quote', label: 'QUOTE', index: '06' },
] as const

type StageId = (typeof STAGE_DEFS)[number]['id']

interface StageState {
  status: 'pending' | 'active' | 'complete'
  summary: string
}

const INIT_STAGES: Record<StageId, StageState> = {
  requirements: { status: 'pending', summary: '' },
  parts: { status: 'pending', summary: '' },
  pcb: { status: 'pending', summary: '' },
  enclosure: { status: 'pending', summary: '' },
  assembly: { status: 'pending', summary: '' },
  quote: { status: 'pending', summary: '' },
}

const STAGE_TIMELINE: { delay: number; stage: StageId; msg: string }[] = [
  { delay: 0, stage: 'requirements', msg: 'ANALYZING PROMPT' },
  { delay: 6000, stage: 'parts', msg: 'SCANNING 14,758 ITEMS' },
  { delay: 20000, stage: 'pcb', msg: 'DESIGNING CIRCUIT' },
  { delay: 34000, stage: 'enclosure', msg: 'GENERATING OPENSCAD' },
  { delay: 46000, stage: 'assembly', msg: 'CREATING BUILD GUIDE' },
  { delay: 56000, stage: 'quote', msg: 'COMPUTING COST' },
]

const LOG_SIM: { delay: number; entry: LogEntry }[] = [
  { delay: 0, entry: { prefix: 'SYS', message: 'BUILD SEQUENCE INIT', status: 'RUN' } },
  { delay: 800, entry: { prefix: 'SYS', message: 'DB LOADED: 14,758 PARTS', status: 'OK' } },
  { delay: 3000, entry: { prefix: 'CORE', message: 'PARSING REQUIREMENTS', status: 'ACT' } },
  { delay: 6000, entry: { prefix: 'CORE', message: 'REQUIREMENTS ANALYZED', status: 'OK' } },
  { delay: 8000, entry: { prefix: 'PARTS', message: 'FTS SEARCH ACTIVE', status: 'ACT' } },
  { delay: 14000, entry: { prefix: 'PARTS', message: 'CANDIDATES MATCHED', status: 'OK' } },
  { delay: 20000, entry: { prefix: 'PARTS', message: 'BOM FINALIZED', status: 'OK' } },
  { delay: 22000, entry: { prefix: 'PCB', message: 'CIRCUIT DESIGN', status: 'ACT' } },
  { delay: 28000, entry: { prefix: 'PCB', message: 'SCHEMATIC GENERATED', status: 'OK' } },
  { delay: 34000, entry: { prefix: 'PCB', message: 'BOARD LAYOUT DONE', status: 'OK' } },
  { delay: 36000, entry: { prefix: 'CAD', message: 'OPENSCAD BODY', status: 'ACT' } },
  { delay: 42000, entry: { prefix: 'CAD', message: 'OPENSCAD LID', status: 'ACT' } },
  { delay: 46000, entry: { prefix: 'CAD', message: 'ENCLOSURE WRITTEN', status: 'OK' } },
  { delay: 48000, entry: { prefix: 'ASM', message: 'STEP GENERATION', status: 'ACT' } },
  { delay: 56000, entry: { prefix: 'ASM', message: 'GUIDE COMPLETE', status: 'OK' } },
  { delay: 58000, entry: { prefix: 'COST', message: 'COMPUTING QUOTE', status: 'ACT' } },
]

const EXAMPLES = [
  '带 GPS 和 FPV 摄像头的自动驾驶无人机',
  '桌面比特币涨跌提醒器，连 Wi-Fi，OLED 大字显示',
  '自动定时喂猫器，早上 7 点出粮，带手动按键',
  '口袋复古游戏机，Type-C 充电，锂电池',
]

/* ═══════════════════════════════════════════
   SLIDER DRAG
   ═══════════════════════════════════════════ */

function startDrag(
  e: React.MouseEvent,
  setter: (v: number) => void,
  min: number, max: number, precision: number,
) {
  const container = e.currentTarget as HTMLDivElement
  const thumb = container.querySelector('.slider-thumb') as HTMLDivElement
  const onMove = (ev: MouseEvent) => {
    const rect = container.getBoundingClientRect()
    const x = Math.max(0, Math.min(ev.clientX - rect.left, rect.width))
    const pct = x / rect.width
    thumb.style.left = `${pct * 100}%`
    setter(Number((min + pct * (max - min)).toFixed(precision)))
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  onMove(e.nativeEvent as unknown as MouseEvent)
}

/* ═══════════════════════════════════════════
   APP
   ═══════════════════════════════════════════ */

export default function App() {
  const [appState, setAppState] = useState<AppState>('idle')
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<BuildResponse | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [footerMsg, setFooterMsg] = useState('WAITING FOR INPUT')
  const [stages, setStages] = useState<Record<StageId, StageState>>({ ...INIT_STAGES })
  const [expanded, setExpanded] = useState<StageId | null>(null)
  const [dbStats, setDbStats] = useState<{ total_parts: number; categories: number } | null>(null)
  const [activeWave, setActiveWave] = useState(0)
  const [pBudget, setPBudget] = useState(100)
  const [pQuality, setPQuality] = useState(0.80)
  const timers = useRef<number[]>([])

  useEffect(() => { getStats().then(setDbStats).catch(() => {}) }, [])

  /* ─── Build handler ─── */
  const handleBuild = useCallback(async () => {
    if (!prompt.trim()) return
    setAppState('building')
    setResult(null)
    setExpanded(null)
    setLogs([])
    setStages({ ...INIT_STAGES })
    setFooterMsg('INITIALIZING...')

    // SSE streaming with simulated stage timeline fallback
    let useStreaming = true
    let streamedResult: BuildResponse | null = null

    // Start simulated stage timeline (overridden by SSE if available)
    STAGE_TIMELINE.forEach(({ delay, stage, msg }, i) => {
      timers.current.push(window.setTimeout(() => {
        if (useStreaming) return // SSE took over
        setStages(prev => {
          const next = { ...prev }
          if (i > 0) {
            const prevId = STAGE_TIMELINE[i - 1].stage
            next[prevId] = { status: 'complete', summary: 'DONE' }
          }
          next[stage] = { status: 'active', summary: msg }
          return next
        })
        setFooterMsg(msg)
      }, delay))
    })

    LOG_SIM.forEach(({ delay, entry }) => {
      timers.current.push(window.setTimeout(() => {
        setLogs(prev => [...prev, entry])
      }, delay))
    })

    // Try SSE streaming first
    try {
      for await (const event of buildProjectStream(prompt)) {
        if (event.type === 'status') {
          useStreaming = true
          const msg = event.data?.message || ''
          setLogs(prev => [...prev, { prefix: 'SSE', message: msg.slice(0, 40).toUpperCase(), status: 'ACT' }])
          setFooterMsg(msg.toUpperCase())
          // Map status messages to stages
          const stageMap: Record<string, StageId> = {
            'analyz': 'requirements', 'select': 'parts', 'pcb': 'pcb', 'design': 'pcb',
            'enclosure': 'enclosure', 'cad': 'enclosure', 'assembly': 'assembly', 'assembl': 'assembly',
            'quote': 'quote', 'cost': 'quote',
          }
          for (const [keyword, stage] of Object.entries(stageMap)) {
            if (msg.toLowerCase().includes(keyword)) {
              setStages(prev => ({ ...prev, [stage]: { status: 'active', summary: msg.slice(0, 30) } }))
              break
            }
          }
        } else if (event.type === 'result') {
          streamedResult = event.data
        } else if (event.type === 'error') {
          throw new Error(event.data?.error || 'Build failed')
        }
      }

      timers.current.forEach(clearTimeout)
      timers.current = []

      const data = streamedResult || await buildProject(prompt)

      const p = data.project
      const bd = p.quote?.breakdown || {}
      const conns = p.pcb_design?.circuit_design?.connections || []

      setStages({
        requirements: { status: 'complete', summary: p.requirements?.project_name || 'ANALYZED' },
        parts: { status: 'complete', summary: `${p.bom.length} items · $${(bd.parts?.total || 0).toLocaleString('en-US')}` },
        pcb: { status: 'complete', summary: `${conns.length} conn · ${p.pcb_design?.layout?.layers || 2}L` },
        enclosure: { status: 'complete', summary: `${p.cad_files.length} files · ${bd['3d_printing']?.material || 'PLA'}` },
        assembly: { status: 'complete', summary: `${(p.assembly?.steps || []).length} steps · ${p.assembly?.difficulty || '?'}` },
        quote: { status: 'complete', summary: `$${p.total_cost.toLocaleString('en-US')}` },
      })

      // Build final log from real data
      const finalLogs: LogEntry[] = [
        { prefix: 'SYS', message: 'BUILD SEQUENCE INIT', status: 'OK' },
        { prefix: 'CORE', message: `"${prompt.slice(0, 28).toUpperCase()}"`, status: 'OK' },
      ]
      for (const al of data.agent_log || []) {
        finalLogs.push({
          prefix: al.agent.slice(0, 6).toUpperCase().padEnd(6),
          message: `${al.task.slice(0, 24).toUpperCase()} [${(al.duration_ms / 1000).toFixed(1)}s]`,
          status: al.error ? 'ERR' : 'OK',
        })
      }
      finalLogs.push({ prefix: 'BOM', message: `${p.bom.length} ITEMS SELECTED`, status: 'OK' })
      finalLogs.push({ prefix: 'SYS', message: `TOTAL: $${p.total_cost.toLocaleString('en-US')}`, status: 'OK' })
      finalLogs.push({ prefix: 'SYS', message: 'BUILD COMPLETE', status: 'OK' })

      setLogs(finalLogs)
      setResult(data)
      setAppState('complete')
      setFooterMsg(`COMPLETE — ${p.bom.length} PARTS — $${p.total_cost.toLocaleString('en-US')}`)
    } catch (e: any) {
      timers.current.forEach(clearTimeout)
      timers.current = []
      setAppState('error')
      setFooterMsg(`ERROR: ${e.message || 'UNKNOWN'}`)
      setLogs(prev => [...prev, { prefix: 'ERR', message: (e.message || 'UNKNOWN').toUpperCase().slice(0, 30), status: 'ERR' }])
    }
  }, [prompt])

  const handleReset = () => {
    setAppState('idle')
    setPrompt('')
    setResult(null)
    setLogs([])
    setStages({ ...INIT_STAGES })
    setExpanded(null)
    setFooterMsg('WAITING FOR INPUT')
  }

  const toggleExpand = (id: StageId) => {
    if (stages[id].status !== 'complete' || !result) return
    setExpanded(prev => (prev === id ? null : id))
  }

  const statusText = appState === 'idle' ? 'IDLE' : appState === 'building' ? 'RUNNING' : appState === 'complete' ? 'COMPLETE' : 'ERROR'
  const proj = result?.project

  /* ═══════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════ */

  return (
    <div className="app-frame">
      {/* ═══ HEADER ═══ */}
      <div className="header">
        <div className="header-group">
          <div className="header-item"><span>[</span> <b>HARDWARE_BUILDER</b> <span>]</span></div>
          <div className="header-item">
            <span className={appState === 'building' ? 'blink' : ''}>►</span>{' '}
            <b>{statusText}</b>
          </div>
        </div>
        <div className="header-group">
          <div className="header-item">
            <span>PARTS</span> <b>{dbStats ? dbStats.total_parts.toLocaleString() : '---'}</b>
          </div>
          <div className="header-item">
            <span>CAT</span> <b>{dbStats ? dbStats.categories : '---'}</b>
          </div>
        </div>
      </div>

      {/* ═══ CONTENT ═══ */}
      <div className="content">
        <MatrixPanel mode={appState} logs={logs} />

        <div className="workspace">
          {appState === 'idle' ? (
            /* ─────── IDLE VIEW ─────── */
            <>
              <div className="prompt-hero">
                <div className="prompt-hero-label">
                  <span>[ 00 ]</span>
                  <span className="sep" />
                  <span>INPUT</span>
                </div>
                <div className="prompt-hero-title">
                  Describe what you want to build.
                </div>
                <input
                  className="prompt-input"
                  type="text"
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleBuild()}
                  placeholder="例如：自动驾驶无人机、比特币提醒器、自动喂猫器..."
                />
                <div className="example-list">
                  {EXAMPLES.map(ex => (
                    <div key={ex} className="example-item" onClick={() => setPrompt(ex)}>
                      {ex}
                    </div>
                  ))}
                </div>
                <div className="prompt-actions">
                  <button className="btn-primary" disabled={!prompt.trim()} onClick={handleBuild}>
                    Initialize Build
                  </button>
                </div>
              </div>

              {/* Config sliders */}
              <div className="section-label">
                <span>Configuration</span>
                <div className="wave-selector">
                  {[
                    <path key="s" d="M0 12 C5 12, 5 0, 10 0 S 15 12, 20 12" />,
                    <polyline key="q" points="0,12 5,12 5,0 15,0 15,12 20,12" />,
                    <polyline key="t" points="0,12 10,0 20,12" />,
                  ].map((svg, i) => (
                    <div key={i} className={`wave-opt ${activeWave === i ? 'active' : ''}`} onClick={() => setActiveWave(i)}>
                      <svg viewBox="0 0 20 12">{svg}</svg>
                    </div>
                  ))}
                </div>
              </div>
              <div className="param-grid">
                <div className="param-cell">
                  <div className="param-header">
                    <span>BUDGET</span><span className="param-val">${pBudget}</span>
                  </div>
                  <div className="slider-container" onMouseDown={e => startDrag(e, setPBudget, 500, 10000, 0)}>
                    <div className="slider-track" />
                    <div className="slider-thumb" style={{ left: `${((pBudget - 10) / 490) * 100}%` }} />
                  </div>
                </div>
                <div className="param-cell">
                  <div className="param-header">
                    <span>QUALITY</span><span className="param-val">{pQuality.toFixed(2)}</span>
                  </div>
                  <div className="slider-container" onMouseDown={e => startDrag(e, setPQuality, 0.1, 1.0, 2)}>
                    <div className="slider-track" />
                    <div className="slider-thumb" style={{ left: `${((pQuality - 0.1) / 0.9) * 100}%` }} />
                  </div>
                </div>
              </div>

              {/* Graphs */}
              <div className="section-label">
                <span>System Metrics</span><span style={{ color: 'var(--dim)' }}>FLT.32</span>
              </div>
              <div className="graph-area">
                <LiveGraph label="SIGNAL" speed={0.05} />
                <LiveGraph label="THROUGHPUT" speed={0.02} />
              </div>
            </>
          ) : (
            /* ─────── BUILD / COMPLETE VIEW ─────── */
            <>
              {/* Compact prompt bar */}
              <div className="prompt-bar">
                <div className="prompt-bar-text">
                  <span>PROMPT</span> "{prompt}"
                </div>
                {appState === 'complete' && (
                  <button className="btn-primary btn-sm" onClick={handleReset}>New Build</button>
                )}
              </div>

              {/* Stage cards */}
              {STAGE_DEFS.map(def => {
                const s = stages[def.id]
                const isExpanded = expanded === def.id
                const canExpand = s.status === 'complete' && !!result

                return (
                  <div key={def.id} className={`stage-card ${s.status} fade-in`}>
                    <div
                      className={`stage-header ${canExpand ? 'stage-clickable' : ''}`}
                      onClick={() => toggleExpand(def.id)}
                    >
                      <span className="stage-idx">[ {def.index} ]</span>
                      <span className="stage-sep" />
                      <span className="stage-label">{def.label}</span>
                      <span className="stage-sep-grow" />
                      {s.summary && <span className="stage-summary">{s.summary}</span>}
                      <span className="stage-sep" />
                      <span className="stage-status">
                        {s.status === 'complete' ? (isExpanded ? '−' : '+')
                          : s.status === 'active' ? '►'
                          : '·'}
                      </span>
                    </div>

                    {/* Expanded detail */}
                    {isExpanded && proj && (
                      <div
                        className="stage-detail"
                        style={def.id === 'parts' ? { maxHeight: 400, padding: 0, overflow: 'hidden' } : undefined}
                      >
                        <div className="bracket-corner bl-tl" />
                        <div className="bracket-corner bl-tr" />
                        <div className="bracket-corner bl-br" />
                        <div className="bracket-corner bl-bl" />
                        {renderDetail(def.id, proj)}
                      </div>
                    )}
                  </div>
                )
              })}

              {/* Graphs */}
              <div style={{ marginTop: 'auto' }}>
                <div className="section-label">
                  <span>Metrics</span><span style={{ color: 'var(--dim)' }}>FLT.32</span>
                </div>
                <div className="graph-area">
                  <LiveGraph label="PROGRESS" speed={0.05} active={appState === 'building'} />
                  <LiveGraph label="COST" speed={0.02} active={appState === 'building'} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ FOOTER ═══ */}
      <div className="footer">
        <div className="footer-group"><span>LOG_OUT: {footerMsg}</span></div>
        <div className="footer-group">
          <span>.py</span><span>.kicad</span><span>.scad</span>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   DETAIL RENDERERS
   ═══════════════════════════════════════════ */

function renderDetail(stageId: StageId, proj: BuildResponse['project']) {
  switch (stageId) {
    case 'requirements': return <RequirementsDetail proj={proj} />
    case 'parts': return <PartsDetail proj={proj} />
    case 'pcb': return <PCBDetail proj={proj} />
    case 'enclosure': return <EnclosureDetail proj={proj} />
    case 'assembly': return <AssemblyDetail proj={proj} />
    case 'quote': return <QuoteDetail proj={proj} />
  }
}

function RequirementsDetail({ proj }: { proj: BuildResponse['project'] }) {
  const req = proj.requirements || {}
  return (
    <div className="param-grid">
      {Object.entries(req).slice(0, 8).map(([key, val]) => (
        <div className="param-cell" key={key}>
          <div className="param-header">
            <span>{key.replace(/_/g, ' ').toUpperCase().slice(0, 16)}</span>
            <span className="param-val">
              {typeof val === 'string' ? val.slice(0, 20) : Array.isArray(val) ? val.length : String(val).slice(0, 20)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function PartsDetail({ proj }: { proj: BuildResponse['project'] }) {
  return (
    <PartsGraph
      bom={proj.bom}
      connections={proj.pcb_design?.circuit_design?.connections || []}
    />
  )
}

function PCBDetail({ proj }: { proj: BuildResponse['project'] }) {
  const pcb = proj.pcb_design || {}
  const circuit = pcb.circuit_design || {}
  const layout = pcb.layout || {}
  const conns = circuit.connections || []
  const rails = circuit.power_rails || []
  return (
    <div>
      <div className="param-grid">
        <div className="param-cell"><div className="param-header"><span>CONNECTIONS</span><span className="param-val">{conns.length}</span></div></div>
        <div className="param-cell"><div className="param-header"><span>LAYERS</span><span className="param-val">{layout.layers || 2}</span></div></div>
        <div className="param-cell"><div className="param-header">
          <span>BOARD</span>
          <span className="param-val">{layout.dimensions_mm?.width || circuit.board_dimensions?.width || 60}×{layout.dimensions_mm?.height || circuit.board_dimensions?.height || 40}mm</span>
        </div></div>
        <div className="param-cell"><div className="param-header"><span>RAILS</span><span className="param-val">{rails.length}</span></div></div>
      </div>
      {conns.slice(0, 15).map((c: any, i: number) => (
        <div className="result-row" key={i}>
          <div className="result-row-text">{c.from} → {c.to}</div>
          <div className="result-row-meta">{c.type}</div>
        </div>
      ))}
      {conns.length > 15 && (
        <div style={{ padding: '6px 12px', color: 'var(--dim)' }}>+ {conns.length - 15} more</div>
      )}
    </div>
  )
}

function EnclosureDetail({ proj }: { proj: BuildResponse['project'] }) {
  const pb = proj.quote?.breakdown?.['3d_printing'] || {}
  return (
    <div>
      <div className="param-grid">
        <div className="param-cell"><div className="param-header"><span>MATERIAL</span><span className="param-val">{pb.material || 'PLA'}</span></div></div>
        <div className="param-cell"><div className="param-header"><span>WEIGHT</span><span className="param-val">{pb.weight_grams || 45}g</span></div></div>
        <div className="param-cell"><div className="param-header"><span>LAYER_H</span><span className="param-val">0.2mm</span></div></div>
        <div className="param-cell"><div className="param-header"><span>INFILL</span><span className="param-val">20%</span></div></div>
      </div>
      {proj.cad_files.map((f, i) => (
        <div className="result-row" key={i}>
          <div className="result-row-text">[{String(i).padStart(2, '0')}] {f.split('/').pop()}</div>
          <div className="result-row-meta">.scad</div>
        </div>
      ))}
      {proj.cad_files.length === 0 && <div style={{ padding: '8px 12px', color: 'var(--dim)' }}>NO CAD FILES</div>}
    </div>
  )
}

function AssemblyDetail({ proj }: { proj: BuildResponse['project'] }) {
  const asm = proj.assembly || {}
  const steps = asm.steps || []
  return (
    <div>
      <div className="param-grid">
        <div className="param-cell"><div className="param-header"><span>DIFFICULTY</span><span className="param-val">{(asm.difficulty || 'N/A').toUpperCase()}</span></div></div>
        <div className="param-cell"><div className="param-header"><span>EST_TIME</span><span className="param-val">{asm.estimated_time_hours || '?'}H</span></div></div>
      </div>
      {steps.map((s: any, i: number) => (
        <div className="step-row" key={i}>
          <div>
            <span className="step-idx">[{String(s.step || i + 1).padStart(2, '0')}]</span>
            <span className="step-title">{s.title}</span>
          </div>
          {s.description && <div className="step-desc">{s.description}</div>}
        </div>
      ))}
    </div>
  )
}

function QuoteDetail({ proj }: { proj: BuildResponse['project'] }) {
  const q = proj.quote || {}
  const bd = q.breakdown || {}
  const items = [
    { key: 'parts', label: 'COMPONENTS' },
    { key: 'pcb_fabrication', label: 'PCB FAB' },
    { key: '3d_printing', label: '3D PRINT' },
    { key: 'assembly', label: 'ASSEMBLY' },
    { key: 'shipping', label: 'SHIPPING' },
    { key: 'platform_fee', label: 'PLATFORM' },
  ]
  return (
    <div>
      {items.map(({ key, label }) => {
        const s = bd[key]
        if (!s) return null
        return (
          <div className="result-row" key={key}>
            <div className="result-row-text">{label}</div>
            <div className="result-row-meta">${(s.total || 0).toLocaleString('en-US')}</div>
          </div>
        )
      })}
      <div className="result-row" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
        <div className="result-row-text result-row-highlight">TOTAL</div>
        <div className="result-row-meta result-row-highlight" style={{ fontSize: 14 }}>${(q.total || 0).toLocaleString('en-US')}</div>
      </div>
      {(q.notes || []).map((n: string, i: number) => (
        <div key={i} style={{ padding: '4px 12px', color: 'var(--dim)', fontSize: 10 }}>• {n}</div>
      ))}
    </div>
  )
}
