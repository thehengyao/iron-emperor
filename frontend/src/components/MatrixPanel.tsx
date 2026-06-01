import { useEffect, useRef, useState } from 'react'
import type { AppState, LogEntry } from '../lib/types'

const ROW_COUNT = 16

function genHex() {
  return Math.floor(Math.random() * 0xffff)
    .toString(16)
    .toUpperCase()
    .padStart(4, '0')
}

interface MatrixPanelProps {
  mode: AppState
  logs: LogEntry[]
}

export default function MatrixPanel({ mode, logs }: MatrixPanelProps) {
  const [idleRows, setIdleRows] = useState<string[]>(
    () => Array.from({ length: ROW_COUNT }, () => '-- -- -- --')
  )
  const [scanRow, setScanRow] = useState(0)
  const posRef = useRef(0)

  // ── Idle animation (CORTEX-style hex cycling) ──
  useEffect(() => {
    if (mode !== 'idle') return

    const iv = setInterval(() => {
      const pos = posRef.current
      setIdleRows((prev) => {
        const next = [...prev]
        next[pos] = `${genHex()} ${genHex()} [ACT]`
        return next
      })
      setScanRow(pos)
      posRef.current = (pos + 1) % ROW_COUNT
    }, 120)

    return () => clearInterval(iv)
  }, [mode])

  // ── Build mode: scanner follows latest log ──
  useEffect(() => {
    if (mode !== 'idle') {
      setScanRow(Math.min(Math.max(logs.length - 1, 0), ROW_COUNT - 1))
    }
  }, [mode, logs.length])

  // ── Compute display data ──
  const getRow = (i: number) => {
    if (mode === 'idle') {
      return {
        text: idleRows[i],
        status: ':',
        highlight: i === scanRow,
      }
    }

    const offset = Math.max(0, logs.length - ROW_COUNT)
    const entry = logs[offset + i]
    if (!entry) {
      return { text: '-- -- -- --', status: ':', highlight: false }
    }

    const statusChar =
      entry.status === 'OK'
        ? '✓'
        : entry.status === 'ERR'
          ? '!'
          : entry.status === 'ACT'
            ? '►'
            : entry.status === 'RUN'
              ? '~'
              : ':'

    return {
      text: `${entry.prefix.padEnd(6)} ${entry.message}`,
      status: statusChar,
      highlight: offset + i === logs.length - 1 && mode === 'building',
    }
  }

  const headerLabel = mode === 'idle' ? 'WEIGHT_HASH' : 'AGENT_LOG'

  return (
    <div className="matrix-panel">
      <div className="matrix-header">
        <div>IDX</div>
        <div style={{ textAlign: 'left', paddingLeft: 12 }}>{headerLabel}</div>
        <div>ST</div>
      </div>
      <div className="matrix-grid">
        {Array.from({ length: ROW_COUNT }, (_, i) => {
          const row = getRow(i)
          return (
            <div className="matrix-row" key={i}>
              <div className="row-idx">
                {i.toString(16).toUpperCase().padStart(2, '0')}
              </div>
              <div
                className="row-data"
                style={{ color: row.highlight ? '#fff' : undefined }}
              >
                {row.text}
              </div>
              <div className="row-meta">{row.status}</div>
            </div>
          )
        })}
        <div
          className="scanner-bar"
          style={{
            top: scanRow * 24,
            display: scanRow >= 0 ? 'block' : 'none',
          }}
        />
      </div>
    </div>
  )
}
