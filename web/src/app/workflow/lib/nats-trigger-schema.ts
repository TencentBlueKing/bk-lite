import type { JsonSchema } from './types';

/**
 * 编排 NATS 触发器默认 input_schema。
 * 字段对齐告警经 system_mgmt 打进编排托管 NATS 的事件 payload
 *（message / team / user_ids，以及可选的 object_id / scene）。
 */
export function buildNatsAlertEnvelopeSchema(): JsonSchema {
  return {
    type: 'object',
    properties: {
      message: { type: 'string', title: '告警/输入内容', maxLength: 50000 },
      team: { type: 'string', title: '团队' },
      user_ids: { type: 'array', title: '用户', items: { type: 'string' } },
      object_id: { type: 'string', title: '对象ID' },
      scene: { type: 'string', title: '场景' },
    },
    required: [],
    additionalProperties: false,
  };
}
