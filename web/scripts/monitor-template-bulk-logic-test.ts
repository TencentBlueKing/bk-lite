import assert from 'node:assert/strict';

import {
  buildBulkApplyPayload,
  buildPolicyPreview,
  clearTemplateSelection,
  getAssetCollectionTemplateLabels,
  getAssetOrganizationText,
  getPrimaryNoticeType,
  groupPolicyTemplates,
  normalizeBulkConfig,
  selectTemplateGroup,
  toggleTemplateSelection,
} from '../src/app/monitor/(pages)/event/template/templateBulkUtils';

const templates = [
  {
    template_key: 'host-remote:0',
    name: 'CPU 使用率过高',
    description: 'CPU too high',
    metric_name: 'cpu_usage_total',
    template_group: '主机（Host Remote）',
    plugin_id: 11,
    plugin_display_name: 'Host Remote',
  },
  {
    template_key: 'host-remote:1',
    name: '内存使用率过高',
    description: 'Memory too high',
    metric_name: 'mem_used_percent',
    template_group: '主机（Host Remote）',
    plugin_id: 11,
    plugin_display_name: 'Host Remote',
  },
  {
    template_key: 'telegraf:0',
    name: '磁盘使用率过高',
    description: 'Disk too high',
    metric_name: 'disk_used_percent',
    template_group: '主机（Telegraf）',
    plugin_id: 12,
    plugin_display_name: 'Telegraf',
  },
];

const groups = groupPolicyTemplates(templates);
assert.deepEqual(groups.map((group) => ({
  name: group.name,
  total: group.templates.length,
  selected: group.selectedCount,
})), [
  { name: '主机（Host Remote）', total: 2, selected: 0 },
  { name: '主机（Telegraf）', total: 1, selected: 0 },
]);

const selectedOne = toggleTemplateSelection([], templates[0]);
assert.deepEqual(selectedOne, ['host-remote:0']);

const selectedGroup = selectTemplateGroup(selectedOne, groups[0].templates, true);
assert.deepEqual(selectedGroup, ['host-remote:0', 'host-remote:1']);
assert.deepEqual(clearTemplateSelection(), []);

const selectedTemplates = templates.filter((item) => selectedGroup.includes(item.template_key));
const assets = [
  {
    instance_id: "('host-a',)",
    instance_name: 'host-a',
    organization: [7],
    plugins: [{ id: 11, display_name: 'Host Remote' }],
  },
  {
    instance_id: "('host-b',)",
    instance_name: 'host-b',
    organization: [8],
    plugins: [{ id: 11, display_name: 'Host Remote' }],
  },
];
const config = {
  name_prefix: '批量策略',
  enable: true,
  schedule: { type: 'min', value: 5 },
  period: { type: 'min', value: 10 },
  trigger_count: 2,
  notice: true,
  notice_type_ids: [1, 2],
  notice_type: 'email',
  notice_users: ['alice'],
};

const preview = buildPolicyPreview(selectedTemplates, assets, config);
assert.deepEqual(preview.map((item) => item.name), [
  '批量策略-CPU 使用率过高-host-a',
  '批量策略-CPU 使用率过高-host-b',
  '批量策略-内存使用率过高-host-a',
  '批量策略-内存使用率过高-host-b',
]);
assert.equal(preview[0].metricLabel, 'Host Remote - cpu_usage_total');
assert.equal(preview[0].statusLabel, '启用');

const payload = buildBulkApplyPayload({
  monitorObjectId: 3,
  templates: selectedTemplates,
  assets,
  config,
});
assert.equal(payload.monitor_object, 3);
assert.deepEqual(payload.asset_ids, ["('host-a',)", "('host-b',)"]);
assert.deepEqual(payload.templates.map((item) => item.collect_type), [11, 11]);
assert.deepEqual(payload.config.notice_type_ids, [1, 2]);
assert.equal(payload.config.notice_type, 'email');
assert.equal(payload.config.trigger_count, 2);
assert.equal('no_data_level' in payload.config, false);
assert.equal('no_data_alert_name' in payload.config, false);

const defaultTriggerConfig = normalizeBulkConfig({
  ...config,
  trigger_count: undefined,
});
assert.equal(defaultTriggerConfig.trigger_count, 1);

const noDataDisabledConfig = normalizeBulkConfig({
  ...config,
  no_data_enabled: false,
  enable_alerts: ['threshold', 'no_data'],
  no_data_level: 'warning',
  no_data_alert_name: '无数据告警',
});
assert.deepEqual(noDataDisabledConfig.enable_alerts, ['threshold']);
assert.equal('no_data_level' in noDataDisabledConfig, false);
assert.equal('no_data_alert_name' in noDataDisabledConfig, false);

const noDataEnabledConfig = normalizeBulkConfig({
  ...config,
  no_data_enabled: true,
  no_data_period: { type: 'min', value: 5 },
  no_data_level: 'warning',
  no_data_alert_name: '无数据告警',
});
assert.deepEqual(noDataEnabledConfig.enable_alerts, ['threshold', 'no_data']);
assert.deepEqual(noDataEnabledConfig.no_data_period, { type: 'min', value: 5 });
assert.deepEqual(noDataEnabledConfig.no_data_recovery_period, { type: 'min', value: 5 });
assert.equal(noDataEnabledConfig.no_data_level, 'warning');
assert.equal(noDataEnabledConfig.no_data_alert_name, '无数据告警');

const noDataPayload = buildBulkApplyPayload({
  monitorObjectId: 3,
  templates: selectedTemplates,
  assets,
  config: noDataEnabledConfig,
});
assert.equal(noDataPayload.config.no_data_level, 'warning');
assert.equal(noDataPayload.config.no_data_alert_name, '无数据告警');
assert.equal(
  getPrimaryNoticeType([2, 1], [
    { id: 1, channel_type: 'email' },
    { id: 2, channel_type: 'nats' },
  ]),
  'nats'
);
assert.equal(getPrimaryNoticeType([], [{ id: 1, channel_type: 'email' }]), '');

assert.equal(
  getAssetOrganizationText(
    { organization: [7, 8] },
    [
      {
        value: 7,
        label: '生产环境',
        children: [{ value: 8, label: '核心业务' }],
      },
    ]
  ),
  '生产环境,核心业务'
);
assert.deepEqual(
  getAssetCollectionTemplateLabels({
    plugins: [
      { id: 11, display_name: 'Host Remote' },
      { id: 12, name: 'Telegraf' },
      { id: 13 },
    ],
  }),
  ['Host Remote', 'Telegraf', '13']
);

console.log('monitor-template-bulk logic validation passed');
