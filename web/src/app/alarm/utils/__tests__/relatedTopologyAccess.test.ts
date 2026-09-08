import { describe, expect, it } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import {
  RELATED_TOPOLOGY_API_PATH,
  probeRelatedTopologyAccess,
} from '../relatedTopologyAccess';

describe('probeRelatedTopologyAccess', () => {
  it('hides unique center on 403/404 and keeps retryable failures visible', async () => {
    const hidden = await probeRelatedTopologyAccess(async () => {
      throw new HandledRequestError('denied', { status: 403 });
    }, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
    const missing = await probeRelatedTopologyAccess(async () => {
      throw new HandledRequestError('gone', { status: 404 });
    }, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
    const retryable = await probeRelatedTopologyAccess(async () => {
      throw new HandledRequestError('bad gateway', { status: 502 });
    }, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');

    expect(hidden).toBe('hidden');
    expect(missing).toBe('hidden');
    expect(retryable).toBe('retryable');
  });

  it('posts a single inst_uuid and treats success as visible', async () => {
    const calls: unknown[] = [];
    const access = await probeRelatedTopologyAccess(async (url, body) => {
      calls.push([url, body]);
      return { center_inst_uuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' };
    }, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');

    expect(access).toBe('ok');
    expect(calls).toEqual([
      [
        RELATED_TOPOLOGY_API_PATH,
        { inst_uuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' },
      ],
    ]);
  });
});
