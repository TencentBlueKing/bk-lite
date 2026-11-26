import { describe, expect, it } from 'vitest';
import { conditionField, conditionFieldCatalog } from './trigger-condition-fields';
import { buildTriggerPayload, newTriggerNotice, readTriggerActions, readTriggerDraft } from './trigger-config';

describe('触发器编辑数据', () => {
  it('自定义通知只保存正文和渠道，模板通知只保存模板配置', () => {
    const notice = { ...newTriggerNotice(), channels: [{ type: 'im' as const, channel_id: 7, template_id: 14 }] };
    const draft = readTriggerDraft();
    draft.name = '采购通知';
    draft.actions[0] = { ...draft.actions[0], type: 'notice', value: '处理 $ticket_title', notice };
    expect(buildTriggerPayload(draft).config.actions[0]).toEqual({
      type: 'notice', value: '', notice: { ...notice, content_mode: 'template' },
    });
    draft.actions[0].notice = { ...notice, content_mode: 'custom' };
    const custom = buildTriggerPayload(draft).config.actions[0];
    expect(custom).toEqual({
      type: 'notice', value: '处理 $ticket_title',
      notice: { ...notice, content_mode: 'custom', channels: [{ type: 'im', channel_id: 7 }] },
    });
    const reopened = readTriggerDraft({
      id: 1, name: draft.name, event: draft.event, action: 'notice', is_enabled: false,
      config: { actions: [custom] },
    });
    expect(buildTriggerPayload(reopened).config.actions[0]).toEqual(custom);
    reopened.actions[0].value = ' ';
    expect(() => buildTriggerPayload(reopened)).toThrow('itsm.rule.triggerNotifyContentRequired');
  });

  it('旧字段标识只将状态识别为系统变量', () => {
    const catalog = conditionFieldCatalog({
      workflows: [], forms: [], services: [], statuses: [],
      system_fields: [
        { key: '$ticket.creator', label: '提单人', type: 'text' },
        { key: '$ticket.status', label: '工单状态', type: 'text' },
      ],
    }, { mode: 'all' });
    expect(conditionField(catalog, 'creator')).toBeUndefined();
    expect(conditionField(catalog, '$ticket.creator')?.label).toBe('提单人');
    expect(conditionField(catalog, 'status')?.label).toBe('工单状态');
  });

  it('旧版等于条件改用后端运算符，单动作保留', () => {
    const draft = readTriggerDraft({
      id: 8, name: '名称匹配', event: 'ticket_create', action: 'tag', is_enabled: true,
      config: { when: { field: 'title', op: 'eq', value: '演示' }, response: '需复查' },
    });
    expect(buildTriggerPayload(draft)).toEqual({
      name: '名称匹配', event: 'ticket_create', action: 'tag',
      config: {
        scope: { mode: 'all' },
        when: { logic: 'and', items: [{ field: 'title', op: '=', value: '演示' }] },
        actions: [{ type: 'tag', value: '需复查' }],
      },
    });
  });

  it('空条件识别为不限条件，切换为全部后清除旧范围', () => {
    const draft = readTriggerDraft({
      id: 9, name: '结束通知', event: 'ticket_end', action: 'notice', is_enabled: true,
      config: { when: { field: '', op: 'eq', value: '' }, response: '已经结束' },
    });
    draft.scope.workflow_ids = [4];
    expect(buildTriggerPayload(draft).config).toEqual({
      scope: { mode: 'all' }, actions: [{ type: 'notice', value: '已经结束' }],
    });
  });

  it('读取指定通知设置并要求至少一个接收人来源和渠道', () => {
    const draft = readTriggerDraft({
      id: 17, name: '专属通知', event: 'ticket_create', action: 'notice', is_enabled: true,
      config: { actions: [{
        type: 'notice', value: '', notice: {
          recipients: { roles: [], users: ['alice'], group_ids: [], field_keys: [] },
          channels: [{ type: 'im', channel_id: 3, template_id: 7 }, { type: 'site' }],
        },
      }] },
    });
    const action = draft.actions[0].notice!;
    expect(buildTriggerPayload(draft).config.actions).toEqual([{
      type: 'notice', value: '', notice: {
        recipients: { roles: [], users: ['alice'], group_ids: [], field_keys: [] },
        channels: [{ type: 'im', channel_id: 3, template_id: 7 }, { type: 'site' }],
      },
    }]);
    action.recipients.users = [];
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerNotifyRecipientsRequired');
    action.recipients.roles = ['creator'];
    action.channels = [];
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerNotifyChannelsRequired');
  });

  it('嵌套组合保留数值、列表与布尔类型，动作按显示顺序保存', () => {
    const draft = readTriggerDraft({
      id: 10, name: '登记例外', event: 'ticket_create', action: 'tag', is_enabled: false,
      config: {
        scope: { mode: 'exclude', service_ids: [1, 2] },
        when: { logic: 'and', items: [
          { field: 'amount', op: '>=', value: 300 },
          { logic: 'or', items: [
            { field: 'priority', op: 'in', value: ['高', '紧急'] },
            { field: 'external', op: '=', value: true },
          ] },
        ] },
        actions: [{ type: 'tag', value: '例外' }, { type: 'status', value: 'processing' }],
      },
    });
    draft.actions.reverse();
    expect(buildTriggerPayload(draft)).toEqual({
      name: '登记例外', event: 'ticket_create', action: 'status',
      config: {
        scope: { mode: 'exclude', service_ids: [1, 2] },
        when: { logic: 'and', items: [
          { field: 'amount', op: '>=', value: 300 },
          { logic: 'or', items: [
            { field: 'priority', op: 'in', value: ['高', '紧急'] },
            { field: 'external', op: '=', value: true },
          ] },
        ] },
        actions: [{ type: 'status', value: 'processing' }, { type: 'tag', value: '例外' }],
      },
    });
  });

  it('精确保存空字符串条件和旧有文本的空格', () => {
    const draft = readTriggerDraft({
      id: 12, name: '文本原样匹配', event: 'ticket_create', action: 'tag', is_enabled: true,
      config: { when: { logic: 'or', items: [
        { field: 'subject', op: '=', value: '' },
        { field: 'subject', op: '=', value: ' ' },
      ] }, response: '主题需补充' },
    });
    expect(buildTriggerPayload(draft).config.when).toEqual({
      logic: 'or', items: [{ field: 'subject', op: '=', value: '' }, { field: 'subject', op: '=', value: ' ' }],
    });
  });

  it('历史损坏的条件、范围和动作能打开，并要求修复后保存', () => {
    const item = {
      id: 13, name: '待修复', event: 'ticket_create', action: 'tag', is_enabled: true,
      config: JSON.parse('{"when":"invalid","scope":{"mode":"include","service_ids":"2"},"actions":[null]}'),
    };
    expect(readTriggerActions(item)).toEqual([{ type: 'tag', value: '' }]);
    const draft = readTriggerDraft(item);
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerScopeRequired');
    draft.scope = { mode: 'all' };
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerFieldRequired');
    draft.when.items = [];
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerActionValueRequired');
  });

  it('缺少范围或动作参数时不发送无效规则', () => {
    const draft = readTriggerDraft({
      id: 11, name: '测试', event: 'ticket_end', action: 'tag', is_enabled: true,
      config: { scope: { mode: 'include' }, actions: [{ type: 'tag', value: '测试标记' }] },
    });
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerScopeRequired');
    draft.scope.mode = 'all';
    draft.actions[0].value = ' ';
    expect(() => buildTriggerPayload(draft)).toThrow('itsm.rule.triggerActionValueRequired');
  });
});
