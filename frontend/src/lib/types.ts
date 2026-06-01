export interface Part {
  name: string
  url?: string
  price?: number
  estimated_price?: number
  quantity: number
  category?: string
  reason?: string
}

export interface ProjectSpec {
  prompt: string
  requirements: Record<string, any>
  bom: Part[]
  pcb_design: any
  cad_files: string[]
  assembly: any
  quote: any
  total_cost: number
  currency: string
  delivery_estimate: string
  status: string
  errors: string[]
}

export interface AgentLog {
  agent: string
  task: string
  status: string
  duration_ms: number
  error?: string
}

export interface BuildResponse {
  status: string
  project: ProjectSpec
  agent_log: AgentLog[]
}

export interface LogEntry {
  prefix: string
  message: string
  status: 'RUN' | 'ACT' | 'OK' | 'ERR' | '---'
}

export type AppState = 'idle' | 'building' | 'complete' | 'error'
export type ResultTab = 'bom' | 'pcb' | 'encl' | 'asm' | 'quote'
