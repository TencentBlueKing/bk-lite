import { describe, expect, it } from 'vitest';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';

interface NestedMessages {
  [key: string]: string | NestedMessages;
}

function flattenMessages(nested: NestedMessages, prefix = ''): Record<string, string> {
  return Object.keys(nested).reduce<Record<string, string>>((messages, key) => {
    const value = nested[key];
    const messageKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      messages[messageKey] = value;
    } else {
      Object.assign(messages, flattenMessages(value, messageKey));
    }
    return messages;
  }, {});
}

const zhMessages = flattenMessages(zh as NestedMessages);
const enMessages = flattenMessages(en as NestedMessages);

const keys = [
  'log.event.funcCount',
  'log.event.funcSum',
  'log.event.funcMax',
  'log.event.funcMin',
  'log.event.funcAvg',
  'log.event.funcCountRate',
  'log.event.funcCountDelta',
  'log.event.funcCountUniq',
  'log.event.funcQuantile',
  'log.event.funcRatio',
  'log.event.funcBytesRate',
  'log.event.ratioFilter',
  'log.event.ratioFilterTip',
  'log.event.triggerCount',
  'log.event.triggerCountTip',
  'log.event.keywordTriggerCountTip',
  'log.event.aggregateQueryCriteriaTips',
  'log.event.thresholdNumberValidate',
  'log.event.backfillGapWarning',
  'log.event.streak',
  'log.event.reasonWindowFailed',
  'log.event.noDataWindowLine',
  'log.event.currentWindowEmpty',
  'log.event.verdictWouldTriggerNoData',
  'log.event.reasonDenominatorZero',
  'log.event.bytesRateUnit',
  'log.event.aggregateTemplateVariable',
  'log.event.countRateUnit',
  'log.event.countDeltaTip',
  'log.event.compareKind',
  'log.event.compareKindAbsolute',
  'log.event.compareKindDelta',
  'log.event.compareKindPercent',
  'log.event.compareTo',
  'log.event.compareToPreviousWindow',
  'log.event.compareOffsetHours',
  'log.event.compareOffsetDays',
  'log.event.compareOffsetHoursValue',
  'log.event.compareOffsetDaysValue',
  'log.event.compareToOffset1h',
  'log.event.compareToOffset24h',
  'log.event.compareToOffset7d',
  'log.event.quantileLabel',
  'log.event.percentTip',
  'log.event.reasonBaselineZero',
  'log.event.reasonBaselineMissing',
  'log.event.reasonNotNumeric',
  'log.event.baselineValue',
  'log.event.computedValue',
  'log.event.currentValue',
  'log.event.conditionColumn',
  'log.event.threshold',
  'log.event.matched',
  'log.event.reason',
  'log.event.dryRun',
  'log.event.dryRunResult',
  'log.event.dryRunWindow',
  'log.event.dryRunPreviousWindow',
  'log.event.dryRunNoMatch',
  'log.event.verdictWouldTrigger',
  'log.event.verdictNoTrigger',
  'log.event.verdictMissingBaseline',
  'log.event.verdictNoData',
  'log.event.openInSearch',
  'log.event.currentCount',
  'log.event.previousCount',
  'log.event.countRate',
  'log.event.countDelta',
  'log.event.truncatedHint',
  'log.event.dryRunGroup',
  'log.event.dryRunVerdict',
  'log.event.matchPrefix',
  'log.event.matchSuffix',
  'log.event.termAny',
  'log.event.termAll',
  'log.event.statRow',
  'log.event.compareRow',
  'log.event.triggerRow',
  'log.event.whenResult',
  'log.event.ratioNumerator',
  'log.event.addCondition',
  'log.event.deleteCondition',
  'log.event.conditionIndex',
];

describe('日志策略计算方式文案', () => {
  it('中英文都有新增键且互不相同', () => {
    for (const key of keys) {
      expect(zhMessages[key], key).toBeTruthy();
      expect(enMessages[key], key).toBeTruthy();
      expect(zhMessages[key]).not.toBe(enMessages[key]);
    }
    expect(zhMessages['log.event.compareKindAbsolute']).toBe('当前值');
    expect(enMessages['log.event.compareKindAbsolute']).toBe('Current value');
    expect(zhMessages['log.event.funcCount']).toBe('计数');
    expect(zhMessages['log.event.funcCountRate']).toBe('速率');
    expect(zhMessages['log.event.funcCountDelta']).toBe('变化量');
    expect(enMessages['log.event.funcCountRate']).toBe('Rate');
    expect(enMessages['log.event.funcCountDelta']).toBe('Change');
    expect(zhMessages['log.event.dryRun']).toBe('试算');
    expect(zhMessages['log.event.openInSearch']).toBe('在检索中打开');
    expect(zhMessages['log.event.triggerCountTip']).toBe('连续 N 个检测窗都满足才告警');
    expect(zhMessages['log.event.noDataWindowLine']).toBe('本窗无日志，上一窗 {count} 条');
  });
});
