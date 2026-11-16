import { expect, it, vi } from 'vitest';
import { publishDesignedWorkflow } from './publish-designed-workflow';
it('发布当前画布表单，表单发布失败时不发布流程', async () => {
  const calls: string[] = [];
  const api = { publishForm: vi.fn(async () => { calls.push('form'); }), saveDesign: vi.fn(async () => { calls.push('design'); }), publishWorkflow: vi.fn(async () => { calls.push('workflow'); }) };
  const schema = { version: 1, fields: [{ key: 'choice', type: 'select', label: '选项', fetch: { source: 'dictionary' as const, mode: 'options' as const, resource_key: 'priority' } }] };
  await publishDesignedWorkflow(api, 1, 2, schema, { nodes: [], edges: [] });
  expect(api.publishForm).toHaveBeenCalledWith(2, schema);
  expect(calls).toEqual(['form', 'design', 'workflow']);
  api.publishForm.mockRejectedValueOnce(new Error('无发布权限'));
  await expect(publishDesignedWorkflow(api, 1, 2, schema, { nodes: [], edges: [] })).rejects.toThrow('无发布权限');
  expect(api.publishWorkflow).toHaveBeenCalledTimes(1);
});
