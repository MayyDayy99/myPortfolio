// Built-in price table, USD per million tokens (Anthropic first-party API
// rates, checked October 2026). Estimates only: not the actual bill.
// Cache writes are priced at 1.25x input (5-minute cache).

type Price = { input: number; output: number; cacheRead: number; context: number }

const M = 1_000_000

// Most specific first: the first `match` found in the model id wins.
const TABLE: { match: string; label: string; price: Price }[] = [
  { match: 'fable-5-1', label: 'Fable 5.1', price: { input: 10, output: 50, cacheRead: 0.25, context: M } },
  { match: 'mythos-5-1', label: 'Mythos 5.1', price: { input: 10, output: 50, cacheRead: 0.25, context: M } },
  { match: 'fable-5', label: 'Fable 5', price: { input: 10, output: 50, cacheRead: 1, context: M } },
  { match: 'opus-5-5', label: 'Opus 5.5', price: { input: 4, output: 20, cacheRead: 0.2, context: M } },
  { match: 'opus-5', label: 'Opus 5', price: { input: 5, output: 25, cacheRead: 0.5, context: M } },
  { match: 'opus-4-8', label: 'Opus 4.8', price: { input: 5, output: 25, cacheRead: 0.5, context: M } },
  { match: 'opus-4-7', label: 'Opus 4.7', price: { input: 5, output: 25, cacheRead: 0.5, context: M } },
  { match: 'opus-4-6', label: 'Opus 4.6', price: { input: 5, output: 25, cacheRead: 0.5, context: M } },
  { match: 'opus-4-5', label: 'Opus 4.5', price: { input: 5, output: 25, cacheRead: 0.5, context: 200_000 } },
  { match: 'opus-4', label: 'Opus 4', price: { input: 15, output: 75, cacheRead: 1.5, context: 200_000 } },
  { match: 'sonnet-5-5', label: 'Sonnet 5.5', price: { input: 2, output: 10, cacheRead: 0.2, context: M } },
  { match: 'sonnet-5', label: 'Sonnet 5', price: { input: 2, output: 10, cacheRead: 0.2, context: M } },
  { match: 'sonnet-4-6', label: 'Sonnet 4.6', price: { input: 3, output: 15, cacheRead: 0.3, context: M } },
  { match: 'sonnet-4', label: 'Sonnet 4', price: { input: 3, output: 15, cacheRead: 0.3, context: 200_000 } },
  { match: 'haiku-5-5', label: 'Haiku 5.5', price: { input: 0.1, output: 0.5, cacheRead: 0.01, context: M } },
  { match: 'haiku-4-5', label: 'Haiku 4.5', price: { input: 1, output: 5, cacheRead: 0.1, context: 200_000 } },
  // Bare aliases, as the Agent tool's `model` parameter may name them.
  { match: 'fable', label: 'Fable', price: { input: 10, output: 50, cacheRead: 0.25, context: M } },
  { match: 'opus', label: 'Opus', price: { input: 4, output: 20, cacheRead: 0.2, context: M } },
  { match: 'sonnet', label: 'Sonnet', price: { input: 2, output: 10, cacheRead: 0.2, context: M } },
  { match: 'haiku', label: 'Haiku', price: { input: 0.1, output: 0.5, cacheRead: 0.01, context: M } },
]

const find = (model: string) => {
  const id = model.toLowerCase().replace(/\./g, '-')
  return TABLE.find(row => id.includes(row.match))
}

export type Usage = {
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
}

/** Estimated USD cost of the usage on that model; 0 for a model not in the table. */
export const costOf = (model: string, usage: Usage): number => {
  const row = find(model)
  if (!row) return 0
  const p = row.price
  return (
    (usage.inputTokens * p.input +
      usage.cacheWriteTokens * p.input * 1.25 +
      usage.cacheReadTokens * p.cacheRead +
      usage.outputTokens * p.output) /
    M
  )
}

/** The model's context window in tokens; an id ending `[1m]` is 1M. */
export const contextWindowOf = (model: string): number => {
  if (/\[1m\]$/i.test(model)) return M
  return find(model)?.price.context ?? 200_000
}

/** `claude-opus-5-5` → `Opus 5.5`; an unknown id as given. */
export const modelLabel = (model: string): string => find(model)?.label ?? model
