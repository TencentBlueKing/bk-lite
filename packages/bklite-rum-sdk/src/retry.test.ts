import { requestWithRetry } from './retry';
import { describe, expect, it, vi } from 'vitest';

describe('requestWithRetry', () => {
  it('drains an accepted response before resolving the transport request', async () => {
    const accepted = new Response('accepted', { status: 202 });
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(accepted);

    const response = await requestWithRetry(
      'https://rum.example.test/rum/v1/collect',
      { method: 'POST' },
      { fetch: fetcher },
    );

    expect(response).toBe(accepted);
    expect(response.bodyUsed).toBe(true);
    expect(response.body?.locked).toBe(false);
  });

  it('retries the same batch without keepalive when an accepted response stream fails', async () => {
    const failedResponse = new Response(
      new ReadableStream({
        start(controller) {
          controller.error(
            new TypeError('connection reset while reading the response'),
          );
        },
      }),
      { status: 202 },
    );
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(failedResponse)
      .mockResolvedValueOnce(new Response(null, { status: 202 }));
    const request = {
      method: 'POST',
      headers: { 'X-RUM-Batch-Id': 'accepted-stream-retry' },
      body: '{"stable":true}',
      keepalive: true,
    } satisfies RequestInit;

    await requestWithRetry('https://rum.example.test/rum/v1/collect', request, {
      fetch: fetcher,
      maxRetries: 1,
      sleep: async () => {},
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0]?.[1]).toBe(request);
    expect(fetcher.mock.calls[1]?.[1]).toEqual({
      ...request,
      keepalive: false,
    });
  });

  it.each([408, 429, 502, 503, 504])(
    'retries transient HTTP %s with the exact same RequestInit',
    async (status) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(new Response(null, { status }))
        .mockResolvedValueOnce(new Response(null, { status: 202 }));
      const request = {
        method: 'POST',
        headers: { 'X-RUM-Batch-Id': 'batch-stable' },
        body: '{"stable":true}',
      } satisfies RequestInit;

      await requestWithRetry(
        'https://rum.example.test/rum/v1/collect',
        request,
        {
          fetch: fetcher,
          sleep: async () => {},
        },
      );

      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(fetcher.mock.calls[0]?.[1]).toBe(request);
      expect(fetcher.mock.calls[1]?.[1]).toBe(request);
    },
  );

  it('honors an exposed Retry-After response header', async () => {
    const sleep = vi.fn(async () => {});
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(null, { status: 429, headers: { 'Retry-After': '2' } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 202 }));

    await requestWithRetry(
      'https://rum.example.test/rum/v1/collect',
      { method: 'POST' },
      { fetch: fetcher, sleep },
    );

    expect(sleep).toHaveBeenCalledWith(2_000);
  });

  it('does not shorten Retry-After to the exponential backoff ceiling', async () => {
    const sleep = vi.fn(async () => {});
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(null, { status: 429, headers: { 'Retry-After': '60' } }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 202 }));

    await requestWithRetry(
      'https://rum.example.test/rum/v1/collect',
      { method: 'POST' },
      { fetch: fetcher, sleep, maxDelayMs: 30_000 },
    );

    expect(sleep).toHaveBeenCalledWith(60_000);
  });

  it('does not retry a permanent protocol error', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 400 }));

    await expect(
      requestWithRetry(
        'https://rum.example.test/rum/v1/collect',
        { method: 'POST' },
        {
          fetch: fetcher,
          sleep: async () => {},
        },
      ),
    ).rejects.toMatchObject({ status: 400, retryable: false });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it.each([200, 204])(
    'rejects HTTP %s because only the ingest protocol 202 is success',
    async (status) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status }));

      await expect(
        requestWithRetry(
          'https://rum.example.test/rum/v1/collect',
          { method: 'POST' },
          {
            fetch: fetcher,
            sleep: async () => {},
          },
        ),
      ).rejects.toMatchObject({ status, retryable: false });
      expect(fetcher).toHaveBeenCalledTimes(1);
    },
  );

  it('does not retry HTTP 500 without a gateway retry contract', async () => {
    const status = 500;
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status }));

    await expect(
      requestWithRetry(
        'https://rum.example.test/rum/v1/collect',
        { method: 'POST' },
        {
          fetch: fetcher,
          sleep: async () => {},
        },
      ),
    ).rejects.toMatchObject({ status, retryable: false });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('allows three retries after the first network attempt', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError('offline'));

    await expect(
      requestWithRetry(
        'https://rum.example.test/rum/v1/collect',
        { method: 'POST' },
        {
          fetch: fetcher,
          maxRetries: 3,
          random: () => 1,
          sleep: async () => {},
        },
      ),
    ).rejects.toMatchObject({ retryable: true });
    expect(fetcher).toHaveBeenCalledTimes(4);
  });
});
