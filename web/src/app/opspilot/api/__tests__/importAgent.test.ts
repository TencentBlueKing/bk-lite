// @vitest-environment jsdom

import { renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

const post = vi.hoisted(() => vi.fn(async () => ({ id: 1, name: '助手', notes: [] })));

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: vi.fn(),
    post,
    patch: vi.fn(),
    put: vi.fn(),
    del: vi.fn(),
  }),
}));

import { useSkillApi } from '@/app/opspilot/api/skill';

it('uploads the agent zip as multipart instead of JSON', async () => {
  const { result } = renderHook(() => useSkillApi());
  const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], 'agent.zip', { type: 'application/zip' });
  await result.current.importAgent(file);
  const [url, body, config] = post.mock.calls[0];
  expect(url).toBe('/opspilot/model_provider_mgmt/llm/import_agent/');
  expect(body).toBeInstanceOf(FormData);
  expect((body as FormData).get('file')).toBe(file);
  expect(config).toMatchObject({ headers: { 'Content-Type': 'multipart/form-data' } });
});
