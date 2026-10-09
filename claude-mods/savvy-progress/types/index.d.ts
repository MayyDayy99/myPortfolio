export type AgentStatus = 'running' | 'done' | 'aborted' | 'error'

export type AgentRow = {
  id: string
  description: string
  type: string
  model: string
  effort?: string
  status: AgentStatus
  startedAt: number
  endedAt?: number
  steps: number
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  contextTokens: number
}

export type Batch = {
  turnId: string
  title: string
  agents: AgentRow[]
}

declare module 'claude-code' {
  interface PluginState {
    'savvy-progress': {
      batch: Batch
      turnId: string
      title: string
      now: number
      frame: number
      isFinishedCollapsed: boolean
    }
  }
}
