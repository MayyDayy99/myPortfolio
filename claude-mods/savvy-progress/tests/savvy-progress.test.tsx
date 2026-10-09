import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const SURFACES = ['terminal', 'desktop'] as const
const SCROLL = { offset: 0, bodyRows: 30 }

// What sits beneath the plugin: a clock, an empty roster, and no drawing of
// the engine's own (a band the plugin leaves alone draws nothing).
const engine = (on: On) => {
  const clock = mock.clock(on)
  on('agent.list', () => ({ value: [] }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine's own</Text>
  })
  return clock
}

const spawnInput = (description: string) => ({
  tool_use_id: `toolu_${description}`,
  prompt: 'do it',
  description,
  subagentType: 'general-purpose',
  provider: { plugin: 'engine', tier: 'core' as const },
  parentModel: 'claude-opus-5-5',
  background: false,
  fork: false,
})

test('tracks a subagent from spawn to finish and draws it', async ($, on) => {
  const clock = engine(on)
  let next = 0
  on('agent.spawn', () => ({ model: 'claude-opus-5-5', agentId: `agent-${++next}` }))
  on('turn.start', (_$, e) => ({ turnId: e.turnId }))
  on('turn.step', async function* (_$, e) {
    return {
      turnId: e.turnId,
      index: e.index,
      answer: '',
      toolUses: [],
      stopReason: 'end_turn' as const,
      usage: {
        model: 'claude-opus-5-5',
        input_tokens: 1000,
        output_tokens: 2000,
        cache_read_input_tokens: 37000,
        cache_creation_input_tokens: 0,
      },
    }
  })
  on('turn.complete', (_$, e) => ({ text: e.answer }))

  await $.turn.start({ text: 'JSDoc + greet test', turnId: 'turn-1' })
  await $.agent.spawn(spawnInput('Add JSDoc to src functions'))
  await $.agent.spawn(spawnInput('Write greet() test file'))

  const stream = $.turn.step({ turnId: 'sub-2', index: 0, model: 'claude-opus-5-5', effort: 'low', messageCount: 1, agentId: 'agent-2' })
  await clock.advance(17000)
  for await (const _ of stream) {
    // drain
  }
  await $.turn.complete({
    answer: 'done', durationMs: 17000, isAborted: false, turnId: 'sub-2', agentId: 'agent-2', reason: 'answer',
  })

  for (const surface of SURFACES) {
    const pane = await $.ui.mount({
      plugin: 'savvy-progress',
      surface,
      component: 'Pane',
      requestId: 'agents-info',
      props: { title: 'Agents', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: SCROLL, view: {} },
    })
    expect(await pane.find({ text: /JSDoc \+ greet test/ })).toBeDefined()
    expect(await pane.find({ text: /Running · 1/ })).toBeDefined()
    expect(await pane.find({ text: 'Add JSDoc to src functions' })).toBeDefined()
    expect(await pane.find({ text: /Finished · 1/ })).toBeDefined()
    // 40k context of 1M, 40k tokens, (1000*4 + 37000*0.2 + 2000*20)/1M ≈ $0.05
    expect(await pane.find({ text: /ctx 4% · 40k · ≈\$0\.05/ })).toBeDefined()
    await pane.press({ key: 'finished' })
    expect(await pane.find({ text: 'Write greet() test file' })).toBeUndefined()
    await pane.press({ key: 'finished' })
    await pane.unmount()

    const band = await $.ui.mount({
      plugin: 'savvy-progress',
      surface,
      component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: true, maxRows: 10, bodyColumns: 100, scroll: SCROLL, view: {} },
    })
    expect(await band.find({ text: /Agents 1\/2/ })).toBeDefined()
    await band.unmount()
  }
})

test('the band stays out of the way with no subagents', async ($, on) => {
  engine(on)
  for (const surface of SURFACES) {
    const band = await $.ui.mount({
      plugin: 'savvy-progress',
      surface,
      component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: true, maxRows: 10, bodyColumns: 100, scroll: SCROLL, view: {} },
    })
    expect(await band.find({ text: /Agents \d/ })).toBeUndefined()
    expect(await band.find({ text: "engine's own" })).toBeDefined()
    await band.unmount()
  }
})
