import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('API discovery requests', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('deduplicates identical account requests while the first is in flight', async () => {
    let resolveResponse: ((response: Response) => void) | undefined
    global.fetch = vi.fn(
      () => new Promise<Response>((resolve) => {
        resolveResponse = resolve
      }),
    ) as typeof fetch

    const first = api.accounts('subscription-1')
    const second = api.accounts('subscription-1')

    expect(global.fetch).toHaveBeenCalledTimes(1)

    resolveResponse?.(
      new Response('[]', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(Promise.all([first, second])).resolves.toEqual([[], []])
  })
})