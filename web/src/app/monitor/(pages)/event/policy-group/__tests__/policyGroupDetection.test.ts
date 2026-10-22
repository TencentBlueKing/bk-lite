import { describe, expect, it } from 'vitest';
import {
  buildPolicyGroupDetectionPayload,
  buildPolicyGroupRulePayload,
  defaultConfigTab,
  detectionConfirm,
  detectionDraftFromGroup,
  detectionSaveBlocker,
  policyGroupDetectionBadges,
  policyGroupDetectionNotes,
  ruleEditClosesAlerts,
  ruleEditConfirm,
  ruleEditDraftFromRule,
} from '../policyGroupDetection';

const draft = detectionDraftFromGroup({
  schedule: { type: 'min', value: 1 },
  no_data: {
    enabled: true,
    period: { type: 'min', value: 10 },
    level: 'error',
    alert_name: '{{host}} 无数据',
    recovery_period: { type: 'min', value: 5 },
  },
});

describe('策略组检测配置', () => {
  it('打开无数据时提交频率、名称、检测窗、级别和恢复窗', () => {
    expect(buildPolicyGroupDetectionPayload(4, draft)).toEqual({
      group_id: 4,
      schedule: { type: 'min', value: 1 },
      no_data: {
        enabled: true,
        period: { type: 'min', value: 10 },
        level: 'error',
        alert_name: '{{host}} 无数据',
        recovery_period: { type: 'min', value: 5 },
      },
    });
  });

  it('关闭无数据时只提交开关，名称和窗口不带上', () => {
    expect(buildPolicyGroupDetectionPayload(4, { ...draft, noDataEnabled: false }).no_data).toEqual({
      enabled: false,
    });
  });

  it('不一致时不把空频率填成 5 分钟，也不把无数据画成关闭', () => {
    const unset = detectionDraftFromGroup(
      { schedule: {}, no_data: { enabled: false } },
      { scheduleUniform: false, noDataUniform: false }
    );
    expect(unset).toMatchObject({
      scheduleValue: null,
      noDataEnabled: null,
    });
    expect(detectionSaveBlocker(unset, {
      scheduleUniform: false,
      noDataUniform: false,
      initial: unset,
    })).toBe('没有需要保存的变更');
  });

  it('只改频率时请求里不带无数据，确认文案也不提无数据', () => {
    const initial = detectionDraftFromGroup(
      { schedule: {}, no_data: { enabled: false } },
      { scheduleUniform: false, noDataUniform: false }
    );
    const next = { ...initial, scheduleValue: 2, scheduleUnit: 'min' as const };
    const scope = { scheduleUniform: false, noDataUniform: false, initial };
    const payload = buildPolicyGroupDetectionPayload(4, next, scope);
    expect(payload).toEqual({ group_id: 4, schedule: { type: 'min', value: 2 } });
    expect(payload).not.toHaveProperty('no_data');
    expect(detectionConfirm(payload, initial).content).toBe('保存后这一组按这个频率扫描。');
    expect(detectionConfirm(payload, initial).content).not.toContain('无数据');
    const alreadyOff = detectionDraftFromGroup({
      schedule: { type: 'min', value: 5 },
      no_data: { enabled: false },
    });
    const frequencyOnly = buildPolicyGroupDetectionPayload(4, { ...alreadyOff, scheduleValue: 1 }, {
      scheduleUniform: true,
      noDataUniform: true,
      initial: alreadyOff,
    });
    expect(frequencyOnly.no_data).toEqual({ enabled: false });
    expect(detectionConfirm(frequencyOnly, alreadyOff).content).toBe('保存后这一组按这个频率扫描。');
  });

  it('只关闭无数据时写明会结束未恢复告警', () => {
    const initial = detectionDraftFromGroup(
      { schedule: { type: 'min', value: 2 }, no_data: { enabled: true, alert_name: '中断', period: { type: 'min', value: 10 }, level: 'warning', recovery_period: { type: 'min', value: 5 } } },
      { scheduleUniform: true, noDataUniform: false }
    );
    const next = { ...initial, noDataEnabled: false };
    const payload = buildPolicyGroupDetectionPayload(4, next, {
      scheduleUniform: true,
      noDataUniform: false,
      initial,
    });
    expect(payload.schedule).toEqual({ type: 'min', value: 2 });
    expect(payload.no_data).toEqual({ enabled: false });
    expect(detectionConfirm(payload, initial)).toEqual({
      title: '关闭无数据告警',
      content: '保存后结束未恢复的无数据告警。',
    });
    expect(detectionConfirm({ group_id: 4, no_data: { enabled: false } })).toEqual({
      title: '关闭无数据告警',
      content: '保存后结束未恢复的无数据告警。',
    });
  });

  it('超出频率上限的无数据窗口按原值保留，只改窗口不说结束告警', () => {
    const initial = detectionDraftFromGroup({
      schedule: { type: 'min', value: 2 },
      no_data: {
        enabled: true,
        alert_name: '中断',
        period: { type: 'min', value: 120 },
        level: 'warning',
        recovery_period: { type: 'min', value: 30 },
      },
    });
    expect(initial.noDataPeriodValue).toBe(120);
    expect(initial.noDataRecoveryValue).toBe(30);
    const next = { ...initial, noDataPeriodValue: 90 };
    const payload = buildPolicyGroupDetectionPayload(4, next, {
      scheduleUniform: true,
      noDataUniform: true,
      initial,
    });
    expect(payload.no_data).toMatchObject({ period: { type: 'min', value: 90 } });
    expect(detectionConfirm(payload, initial).content).toBe('保存后按新的无数据条件检测，正在响的无数据告警不结束。');
    expect(detectionSaveBlocker(initial, { scheduleUniform: true, noDataUniform: true, initial })).toBeNull();
  });

  it('检测窗小于恢复窗时不能保存', () => {
    expect(
      detectionSaveBlocker({
        ...draft,
        noDataPeriodValue: 5,
        noDataRecoveryValue: 10,
      })
    ).toBe('无数据检测窗不能小于恢复窗');
  });

  it('频率和无数据各自标出不一致', () => {
    expect(policyGroupDetectionBadges({ scheduleUniform: false, noDataUniform: true })).toEqual(['频率不一致']);
    expect(policyGroupDetectionBadges({ scheduleUniform: true, noDataUniform: false })).toEqual(['无数据不一致']);
    expect(policyGroupDetectionBadges({})).toEqual([]);
  });

  it('不一致时说明保存后会写成同一套', () => {
    expect(policyGroupDetectionNotes({ scheduleUniform: false, noDataUniform: false })).toEqual([
      '组内检测频率不一致，保存后会写成同一套。',
      '组内无数据告警不一致，保存后会写成同一套。',
    ]);
  });

  it('配置抽屉只有响应有缺口时停在响应页，否则停在检测页', () => {
    expect(defaultConfigTab([], ['处理人不一致'])).toBe('notice');
    expect(defaultConfigTab(['频率不一致'], ['处理人不一致'])).toBe('detection');
    expect(defaultConfigTab([], [])).toBe('detection');
  });
});

describe('策略组规则编辑', () => {
  const original = ruleEditDraftFromRule({
    query_type: 'metric',
    threshold: [{ level: 'warning', method: '>', value: 80 }],
    alert_name: 'CPU 过高',
    trigger_count: 1,
    recovery_condition: 1,
    recovery_threshold: {},
  });

  it('只改告警名称不结束告警，确认文案也不提示结束', () => {
    const next = { ...original, alertName: '{{host}} 过高' };
    expect(ruleEditClosesAlerts(original, next)).toBe(false);
    expect(ruleEditConfirm({ closesAlerts: false, alertNameChanged: true, openAlertCount: 2 }).content).toBe(
      '保存后新告警使用新名称。正在响的告警不结束。'
    );
    expect(buildPolicyGroupRulePayload(4, 9, next)).toMatchObject({
      group_id: 4,
      rule_id: 9,
      alert_name: '{{host}} 过高',
      trigger_count: 1,
      recovery_condition: 1,
      recovery_threshold: {},
    });
  });

  it('改连续触发周期或恢复阈值会结束告警', () => {
    expect(ruleEditClosesAlerts(original, { ...original, triggerCount: 3 })).toBe(true);
    expect(
      ruleEditClosesAlerts(original, {
        ...original,
        recoveryThreshold: { method: '<', value: 10 },
      })
    ).toBe(true);
    expect(ruleEditConfirm({ closesAlerts: true, alertNameChanged: false, openAlertCount: 2 }).content).toContain(
      '结束这条规则上 2 条未恢复告警'
    );
  });

  it('多条件规则不提交恢复阈值', () => {
    const multi = ruleEditDraftFromRule({
      query_type: 'multi',
      condition_thresholds: { a: [{ level: 'warning', method: '>', value: 1 }] },
      alert_name: '双高',
      trigger_count: 2,
      recovery_condition: 2,
    });
    const payload = buildPolicyGroupRulePayload(4, 9, multi);
    expect(payload).not.toHaveProperty('recovery_threshold');
    expect(payload.condition_thresholds).toEqual(multi.conditionThresholds);
  });

  it('未填写的恢复阈值和空对象视为没有变化', () => {
    const untouched = {
      ...original,
      recoveryThreshold: { method: '>', value: null },
    };
    expect(ruleEditClosesAlerts(original, untouched)).toBe(false);
  });
});
