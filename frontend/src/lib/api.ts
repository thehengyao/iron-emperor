import type { BuildResponse } from './types'

const BASE = import.meta.env.DEV ? '/api' : ''

export async function buildProject(prompt: string): Promise<BuildResponse> {
  const res = await fetch(`${BASE}/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) throw new Error(`Build failed: ${res.statusText}`)
  return res.json()
}

/**
 * SSE streaming build. Yields {type, data} events.
 * Falls back to regular /build if SSE unavailable.
 */
export async function* buildProjectStream(
  prompt: string,
): AsyncGenerator<{ type: 'status' | 'result' | 'error' | 'done'; data: any }> {
  try {
    const res = await fetch(`${BASE}/build/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    })
    if (!res.ok || !res.body) {
      const data = await buildProject(prompt)
      yield { type: 'result', data }
      yield { type: 'done', data: {} }
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      let eventType = 'status'
      for (const line of lines) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        else if (line.startsWith('data: ')) {
          try {
            yield { type: eventType as any, data: JSON.parse(line.slice(6)) }
          } catch {
            yield { type: eventType as any, data: { message: line.slice(6) } }
          }
        }
      }
    }
  } catch {
    const data = await buildProject(prompt)
    yield { type: 'result', data }
    yield { type: 'done', data: {} }
  }
}

export async function searchParts(query: string, limit = 20) {
  const res = await fetch(`${BASE}/search?q=${encodeURIComponent(query)}&limit=${limit}`)
  return res.json()
}

export async function getStats() {
  const res = await fetch(`${BASE}/stats`)
  return res.json()
}
