import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AgentRow, AgentStatus, Batch } from '../types'
import { CRAB_ROWS, CRAB_WIDTH, crabCells, laneCells } from './crab'
import { contextWindowOf, costOf, modelLabel } from './pricing'

const PANE = 'agents-info'
const TICK_MS = 500

const batch = atom({ plugin: 'savvy-progress', key: 'batch' } as const, { turnId: '', title: '', agents: [] })
const turnId = atom({ plugin: 'savvy-progress', key: 'turnId' } as const, '')
const title = atom({ plugin: 'savvy-progress', key: 'title' } as const, '')
const now = atom({ plugin: 'savvy-progress', key: 'now' } as const, 0)
const frame = atom({ plugin: 'savvy-progress', key: 'frame' } as const, 0)
const isFinishedCollapsed = atom({ plugin: 'savvy-progress', key: 'isFinishedCollapsed' } as const, false)

// --- numbers -----------------------------------------------------------------

const tokensOf = (a: AgentRow) =>
  a.inputTokens + a.outputTokens + a.cacheReadTokens + a.cacheWriteTokens

const agentCost = (a: AgentRow) => costOf(a.model, a)

const contextShare = (a: AgentRow) =>
  Math.min(1, a.contextTokens / contextWindowOf(a.model))

const formatTokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`

const formatCost = (usd: number) => `≈$${usd < 10 ? usd.toFixed(2) : usd.toFixed(0)}`

const formatTime = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000))
  const mm = Math.floor(s / 60) % 60
  const ss = String(s % 60).padStart(2, '0')
  return s >= 3600 ? `${Math.floor(s / 3600)}:${String(mm).padStart(2, '0')}:${ss}` : `${mm}:${ss}`
}

const bar = (share: number, width: number) => {
  const filled = Math.round(Math.max(0, Math.min(1, share)) * width)
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

const elapsedOf = (a: AgentRow, at: number) => (a.endedAt ?? Math.max(at, a.startedAt)) - a.startedAt

const batchTotals = (b: Batch, at: number) => {
  const first = Math.min(...b.agents.map(a => a.startedAt))
  const isRunning = b.agents.some(a => a.status === 'running')
  const last = isRunning ? Math.max(at, first) : Math.max(...b.agents.map(a => a.endedAt ?? a.startedAt))
  return {
    cost: b.agents.reduce((sum, a) => sum + agentCost(a), 0),
    tokens: b.agents.reduce((sum, a) => sum + tokensOf(a), 0),
    elapsed: b.agents.length === 0 ? 0 : last - first,
  }
}

// --- state writes --------------------------------------------------------------

const newRow = (id: string, fields: Partial<AgentRow>, startedAt: number): AgentRow => ({
  id,
  description: fields.description ?? 'Subagent',
  type: fields.type ?? 'agent',
  model: fields.model ?? '',
  effort: fields.effort,
  status: 'running',
  startedAt,
  steps: 0,
  inputTokens: 0,
  outputTokens: 0,
  cacheReadTokens: 0,
  cacheWriteTokens: 0,
  contextTokens: 0,
})

const patchAgent = ($: EngineInterface, id: string, patch: (a: AgentRow) => AgentRow) =>
  update($, batch, b => ({ ...b, agents: b.agents.map(a => (a.id === id ? patch(a) : a)) }))

// A loop the mod never saw spawn (it loaded mid-run): add it from the roster.
const ensureAgent = async ($: EngineInterface, id: string) => {
  const current = await read($, batch)
  if (current.agents.some(a => a.id === id)) return
  const info = (await $.agent.list()).find(one => one.id === id)
  const at = await $.clock.now()
  const row = newRow(id, { description: info?.description, type: info?.type }, at)
  await update($, batch, b => (b.agents.some(a => a.id === id) ? b : { ...b, agents: [...b.agents, row] }))
}

const statusOf = (reason: string): AgentStatus =>
  reason === 'answer' ? 'done' : reason === 'aborted' ? 'aborted' : 'error'

const togglePane = async ($: EngineInterface) => {
  const isOpen = (await $.ui.panes()).some(pane => pane.id === PANE)
  if (isOpen) {
    await $.ui.close({ id: PANE })
    return false
  }
  await $.ui.open({ id: PANE, title: 'Agents' })
  return true
}

// --- hooks ---------------------------------------------------------------------

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'agents-info',
      description: 'Open or close the live panel of subagents: model, progress, tokens and estimated cost',
    })
    $.clock.every(TICK_MS, () => {
      void (async () => {
        const b = await read($, batch)
        if (!b.agents.some(a => a.status === 'running')) return
        const at = await $.clock.now()
        await update($, now, () => at)
        await update($, frame, n => (n + 1) % 1_000_000)
      })()
    })

    return next(e)
  })

  on('command.run', { command: 'agents-info' }, async $ => {
    const isOpen = await togglePane($)

    return { text: isOpen ? 'Agents panel opened.' : 'Agents panel closed.' }
  })

  on('turn.start', async ($, e, next) => {
    const firstLine = e.text.trim().split('\n')[0] ?? ''
    await update($, turnId, () => e.turnId)
    await update($, title, () => (firstLine.length > 48 ? `${firstLine.slice(0, 47)}…` : firstLine))

    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    const spawned = await next(e)
    if (spawned.deny !== undefined || !spawned.agentId) return spawned

    const at = await $.clock.now()
    const row = newRow(spawned.agentId, { description: e.description, type: e.subagentType, model: spawned.model }, at)
    const [currentTurn, currentTitle] = [await read($, turnId), await read($, title)]
    await update($, batch, b => {
      const isStale = b.turnId !== currentTurn && !b.agents.some(a => a.status === 'running')
      return isStale
        ? { turnId: currentTurn, title: currentTitle, agents: [row] }
        : { ...b, agents: [...b.agents.filter(a => a.id !== row.id), row] }
    })
    await update($, now, () => at)

    return spawned
  })

  on('turn.step', async function* ($, e, next) {
    const id = e.agentId
    if (id === undefined) {
      return yield* next(e)
    }

    await ensureAgent($, id)
    await patchAgent($, id, a => ({
      ...a,
      model: e.model || a.model,
      effort: e.effort === undefined ? a.effort : String(e.effort),
      status: 'running',
      endedAt: undefined,
    }))
    const result = yield* next(e)
    const usage = result.usage
    if (usage) {
      await patchAgent($, id, a => ({
        ...a,
        model: usage.model || a.model,
        steps: a.steps + 1,
        inputTokens: a.inputTokens + usage.input_tokens,
        outputTokens: a.outputTokens + usage.output_tokens,
        cacheReadTokens: a.cacheReadTokens + usage.cache_read_input_tokens,
        cacheWriteTokens: a.cacheWriteTokens + usage.cache_creation_input_tokens,
        contextTokens:
          usage.input_tokens +
          usage.cache_read_input_tokens +
          usage.cache_creation_input_tokens +
          usage.output_tokens,
      }))
    }

    return result
  })

  on('turn.complete', async ($, e, next) => {
    const id = e.agentId
    if (id !== undefined) {
      await ensureAgent($, id)
      const at = await $.clock.now()
      const usage = e.usage
      await patchAgent($, id, a => {
        const ended = { ...a, status: statusOf(e.reason), endedAt: at }
        // Steps already counted the usage; take the turn's own when none did.
        return usage && a.steps === 0
          ? {
              ...ended,
              model: usage.model || a.model,
              inputTokens: usage.input_tokens,
              outputTokens: usage.output_tokens,
              cacheReadTokens: usage.cache_read_input_tokens,
              cacheWriteTokens: usage.cache_creation_input_tokens,
            }
          : ended
      })
      await update($, now, () => at)
    }

    return next(e)
  })

  // The band above the prompt: overall progress, and crabs at work.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const b = await read($, batch)
    const running = b.agents.filter(a => a.status === 'running').length
    const isCurrent = b.turnId === (await read($, turnId)) && e.props.isWorking
    if (e.props.hasSurvey || b.agents.length === 0 || (running === 0 && !isCurrent)) {
      return next(e)
    }

    const at = await read($, now)
    const tick = await read($, frame)
    const totals = batchTotals(b, at)
    const finished = b.agents.length - running
    const columns = Math.max(20, e.props.bodyColumns)
    const summary = `${formatCost(totals.cost)} · ${formatTokens(totals.tokens)} tok · ${formatTime(totals.elapsed)}`
    const head = `Agents ${finished}/${b.agents.length} `
    const barWidth = Math.max(6, Math.min(30, columns - head.length - summary.length - 18))

    if (e.surface === 'terminal') {
      const { Box, Button, Raster, Text } = $.ui.resolve(e)
      const laneWidth = Math.max(CRAB_WIDTH, Math.min(columns, 64))
      return (
        <Box flexDirection="column">
          <Box flexDirection="row">
            <Text bold>{head}</Text>
            <Text color="claude">{bar(finished / b.agents.length, barWidth)}</Text>
            <Text dimColor> {summary} </Text>
            <Button key="open" plain label="/agents-info" onPress={() => togglePane($)} />
          </Box>
          {running > 0 && (
            <Raster key="lane" columns={laneWidth} rows={CRAB_ROWS} cells={laneCells(laneWidth, running, tick)} />
          )}
        </Box>
      )
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="row">
        <Text bold>{running > 0 ? '🦀 ' : ''}{head}</Text>
        <Text color="claude">{bar(finished / b.agents.length, barWidth)}</Text>
        <Text dimColor> {summary} </Text>
        <Button key="open" plain label="/agents-info" onPress={() => togglePane($)} />
      </Box>
    )
  })

  // The panel: every subagent of the latest batch, running first.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const b = await read($, batch)
    const at = await read($, now)
    const tick = await read($, frame)
    const isCollapsed = await read($, isFinishedCollapsed)
    const columns = Math.max(24, e.props.bodyColumns)
    const isTerminal = e.surface === 'terminal'
    const els = $.ui.resolve(e)
    const { Box, Button, Text } = els

    if (b.agents.length === 0) {
      return (
        <Box flexDirection="column">
          <Text bold>Agents</Text>
          <Text dimColor>No subagents yet. Give Claude a job big enough to split across helpers.</Text>
        </Box>
      )
    }

    const totals = batchTotals(b, at)
    const running = b.agents.filter(a => a.status === 'running')
    const finished = b.agents.filter(a => a.status !== 'running')
    const barWidth = Math.max(8, columns - CRAB_WIDTH - 2)

    const stat = (key: string, label: string, value: string) => (
      <Box key={key} flexDirection="column" borderStyle="round" borderDimColor paddingX={1} flexGrow={1}>
        <Text dimColor>{label}</Text>
        <Text bold>{value}</Text>
      </Box>
    )

    const crab = (a: AgentRow) => {
      const isDone = a.status !== 'running'
      if (isTerminal && 'Raster' in els) {
        const { Raster } = els
        return (
          <Raster key={`crab-${a.id}`} columns={CRAB_WIDTH} rows={CRAB_ROWS} cells={crabCells(isDone ? 0 : tick, isDone)} />
        )
      }
      return <Text>🦀</Text>
    }

    const row = (a: AgentRow) => {
      const share = contextShare(a)
      const mark =
        a.status === 'running'
          ? <Text color="success">●</Text>
          : a.status === 'done'
            ? <Text color="success">✓</Text>
            : a.status === 'aborted'
              ? <Text color="warning">■</Text>
              : <Text color="error">✗</Text>
      const detail = [a.model && modelLabel(a.model), a.effort].filter(Boolean).join(' · ')
      const meter =
        a.status === 'running'
          ? <Text dimColor>{bar(share, barWidth)}</Text>
          : a.status === 'done'
            ? <Text color="success">{bar(1, barWidth)}</Text>
            : <Text color={a.status === 'error' ? 'error' : 'warning'}>{bar(share, barWidth)}</Text>
      return (
        <Box key={`agent-${a.id}`} flexDirection="row" marginTop={1}>
          <Box width={CRAB_WIDTH + 1} flexShrink={0}>{crab(a)}</Box>
          <Box flexDirection="column" flexGrow={1}>
            <Box flexDirection="row" justifyContent="space-between">
              <Text bold wrap="truncate-end">{a.description}</Text>
              {mark}
            </Box>
            <Text wrap="truncate-end">
              <Text color="success">{a.type}</Text>
              <Text dimColor> {detail}</Text>
            </Text>
            {meter}
            <Text dimColor wrap="truncate-end">
              ctx {Math.round(share * 100)}% · {formatTokens(tokensOf(a))} · {formatCost(agentCost(a))} · {formatTime(elapsedOf(a, at))}
            </Text>
          </Box>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Text bold wrap="truncate-end">{b.title || 'Agents'}</Text>
        <Box flexDirection="row" columnGap={1}>
          {stat('cost', 'Cost', formatCost(totals.cost))}
          {stat('tokens', 'Tokens', formatTokens(totals.tokens))}
          {stat('time', 'Time', formatTime(totals.elapsed))}
        </Box>
        {running.length > 0 && <Text dimColor>Running · {running.length}</Text>}
        {running.map(row)}
        {finished.length > 0 && (
          <Box marginTop={1}>
            <Button key="finished" plain onPress={() => update($, isFinishedCollapsed, v => !v)}>
              {isCollapsed ? '▸' : '▾'} Finished · {finished.length}
            </Button>
          </Box>
        )}
        {!isCollapsed && finished.map(row)}
        <Box marginTop={1}>
          <Text dimColor>Costs are estimates from token counts and a built-in price table, not your bill.</Text>
        </Box>
      </Box>
    )
  })
}
