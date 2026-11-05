import { describe, expect, it } from 'vitest';

import { buildNatsAlertEnvelopeSchema } from '../lib/nats-trigger-schema';
import { commonTriggerInputSchema } from '../lib/canvas-dsl';

describe('NATS 告警信封默认 schema', () => {
  it('声明告警进编排约定字段且不含必填，便于草稿期引用 workflow.input.message', () => {
    const schema = buildNatsAlertEnvelopeSchema();
    expect(Object.keys(schema.properties || {})).toEqual([
      'message',
      'team',
      'user_ids',
      'object_id',
      'scene',
    ]);
    expect(schema.properties?.message).toMatchObject({ type: 'string', title: '告警/输入内容' });
    expect(schema.properties?.team).toMatchObject({ type: 'integer', title: '团队' });
    expect(schema.properties?.user_ids).toMatchObject({ type: 'array', items: { type: 'string' } });
    expect(schema.required).toEqual([]);
    expect(schema.additionalProperties).toBe(false);
  });

  it('单 NATS 触发时公共输入包含 message', () => {
    const common = commonTriggerInputSchema({
      trigger_nodes: [{
        id: 'trigger_nats',
        name: 'K8s告警NATS',
        trigger_type: 'NATS',
        input_schema: buildNatsAlertEnvelopeSchema(),
        config: {},
      }],
    });
    expect(common.properties?.message).toMatchObject({ type: 'string', title: '告警/输入内容' });
  });
});
