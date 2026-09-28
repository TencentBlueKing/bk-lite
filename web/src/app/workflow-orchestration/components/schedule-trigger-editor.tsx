'use client';

import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Select, Spin } from 'antd';

import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { WorkflowPermission } from './workflow-permission';

export type ScheduleFrequency = 'daily' | 'weekly' | 'monthly' | 'crontab';

export interface ScheduleConfig extends Record<string, unknown> {
  frequency: ScheduleFrequency;
  time?: string[];
  weekdays?: number[];
  days?: number[];
  crontab_expression?: string;
}

export interface SchedulePreview {
  config: Record<string, unknown>;
  expressions: string[];
  timezone: string;
  next_runs: string[];
  test_output: Record<string, unknown>;
}

export function normalizeScheduleConfig(value: Record<string, unknown>): ScheduleConfig {
  const frequency = value.frequency as ScheduleFrequency | undefined;
  if (frequency === 'weekly') return { frequency, time: normalizedTimes(value.time), weekdays: normalizedNumbers(value.weekdays, [1]) };
  if (frequency === 'monthly') return { frequency, time: normalizedTimes(value.time), days: normalizedNumbers(value.days, [1]) };
  if (frequency === 'crontab') return { frequency, crontab_expression: String(value.crontab_expression || value.expression || '0 2 * * *') };
  if (!frequency && value.expression) return { frequency: 'crontab', crontab_expression: String(value.expression) };
  return { frequency: 'daily', time: normalizedTimes(value.time) };
}

function normalizedTimes(value: unknown) {
  if (Array.isArray(value) && value.length) return value.map(String);
  if (typeof value === 'string' && value) return [value];
  return ['02:00'];
}

function normalizedNumbers(value: unknown, fallback: number[]) {
  return Array.isArray(value) && value.length ? value.filter((item): item is number => typeof item === 'number') : fallback;
}

function cleanConfig(config: ScheduleConfig): ScheduleConfig {
  if (config.frequency === 'crontab') return { frequency: 'crontab', crontab_expression: config.crontab_expression || '' };
  if (config.frequency === 'weekly') return { frequency: 'weekly', time: config.time || [], weekdays: config.weekdays || [] };
  if (config.frequency === 'monthly') return { frequency: 'monthly', time: config.time || [], days: config.days || [] };
  return { frequency: 'daily', time: config.time || [] };
}

export function ScheduleTriggerEditor({
  value,
  readOnly,
  preview,
  previewBusy,
  previewError,
  onChange,
}: {
  value: Record<string, unknown>;
  readOnly: boolean;
  preview?: SchedulePreview;
  previewBusy?: boolean;
  previewError?: string;
  onChange: (value: ScheduleConfig) => void;
}) {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const config = normalizeScheduleConfig(value);
  const patch = (next: ScheduleConfig) => onChange(cleanConfig(next));
  const times = config.time || ['02:00'];
  const cronFields = (config.crontab_expression || '0 2 * * *').trim().split(/\s+/);
  while (cronFields.length < 5) cronFields.push('*');
  const changeCronField = (index: number, field: string) => {
    const next = cronFields.slice(0, 5);
    next[index] = field;
    patch({ frequency: 'crontab', crontab_expression: next.join(' ') });
  };

  return <section className="flex flex-col gap-5">
    <Alert type="info" showIcon message={t('workflowOrchestration.editor.scheduleSystemTimezoneHint', '按当前用户的系统时区计算，发布时固化到流程版本。')} />
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.triggerFrequency', '触发频率')} required>
      <Select
        disabled={readOnly}
        value={config.frequency}
        options={[
          { value: 'daily', label: t('workflowOrchestration.editor.everyDay', '每天') },
          { value: 'weekly', label: t('workflowOrchestration.editor.everyWeek', '每周') },
          { value: 'monthly', label: t('workflowOrchestration.editor.everyMonth', '每月') },
          { value: 'crontab', label: t('workflowOrchestration.editor.customCron', '自定义 Cron') },
        ]}
        onChange={(frequency: ScheduleFrequency) => patch(frequency === 'weekly'
          ? { frequency, time: ['02:00'], weekdays: [1] }
          : frequency === 'monthly'
            ? { frequency, time: ['02:00'], days: [1] }
            : frequency === 'crontab'
              ? { frequency, crontab_expression: '0 2 * * *' }
              : { frequency, time: ['02:00'] })}
      />
    </Form.Item>

    {config.frequency === 'weekly' ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.weekdays', '执行星期')} required>
      <Select mode="multiple" disabled={readOnly} value={config.weekdays} options={[
        ['1', t('workflowOrchestration.editor.weekdayMon', '周一')],
        ['2', t('workflowOrchestration.editor.weekdayTue', '周二')],
        ['3', t('workflowOrchestration.editor.weekdayWed', '周三')],
        ['4', t('workflowOrchestration.editor.weekdayThu', '周四')],
        ['5', t('workflowOrchestration.editor.weekdayFri', '周五')],
        ['6', t('workflowOrchestration.editor.weekdaySat', '周六')],
        ['0', t('workflowOrchestration.editor.weekdaySun', '周日')],
      ].map(([value, label]) => ({ value: Number(value), label }))} onChange={(weekdays) => patch({ ...config, weekdays })} />
    </Form.Item> : null}

    {config.frequency === 'monthly' ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.monthDays', '执行日期')} required tooltip={t('workflowOrchestration.editor.monthDaysHint', '选择每月的哪几天执行')}>
      <Select mode="multiple" disabled={readOnly} value={config.days} options={Array.from({ length: 31 }, (_, index) => ({ value: index + 1, label: t('workflowOrchestration.editor.monthDayLabel', '{day} 日', { day: index + 1 }) }))} onChange={(days) => patch({ ...config, days })} />
    </Form.Item> : null}

    {config.frequency !== 'crontab' ? <Form.Item className="mb-0" label={t('workflowOrchestration.editor.executionTime', '执行时间')} required>
      <div className="flex flex-col gap-2">
        {times.map((item, index) => <div key={`${index}-${item}`} className="flex items-center gap-2">
          <Input
            aria-label={t('workflowOrchestration.editor.executionTimeIndex', '执行时间 {index}', { index: index + 1 })}
            type="time"
            disabled={readOnly}
            value={item}
            onChange={(event) => patch({ ...config, time: times.map((current, currentIndex) => currentIndex === index ? event.target.value : current) })}
          />
          {!readOnly && times.length > 1 ? <WorkflowPermission operation="Edit"><Button aria-label={t('workflowOrchestration.editor.deleteExecutionTime', '删除执行时间')} danger icon={<DeleteOutlined />} onClick={() => patch({ ...config, time: times.filter((_, currentIndex) => currentIndex !== index) })} /></WorkflowPermission> : null}
        </div>)}
        {!readOnly && times.length < 10 ? <WorkflowPermission operation="Edit" className="block"><Button type="dashed" icon={<PlusOutlined />} onClick={() => patch({ ...config, time: [...times, '12:00'] })}>{t('workflowOrchestration.editor.addExecutionTime', '添加执行时间')}</Button></WorkflowPermission> : null}
      </div>
    </Form.Item> : <Form.Item className="mb-0" label={t('workflowOrchestration.editor.cronExpression', 'Cron 表达式')} required>
      <div className="grid grid-cols-5 gap-2">
        {[
          t('workflowOrchestration.editor.cronFieldMinute', '分'),
          t('workflowOrchestration.editor.cronFieldHour', '时'),
          t('workflowOrchestration.editor.cronFieldDay', '日'),
          t('workflowOrchestration.editor.cronFieldMonth', '月'),
          t('workflowOrchestration.editor.cronFieldDow', '周'),
        ].map((label, index) => <label key={label} className="text-center text-xs text-[var(--color-text-3)]">
          <span className="mb-1 block">{label}</span>
          <Input disabled={readOnly} value={cronFields[index]} onChange={(event) => changeCronField(index, event.target.value)} />
        </label>)}
      </div>
    </Form.Item>}

    <section className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4">
      <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{t('workflowOrchestration.editor.nextRuns', '下次执行')}</div>
      <Spin spinning={Boolean(previewBusy)}>
        {previewError ? <Alert type="error" showIcon message={previewError} /> : preview?.next_runs?.length
          ? <ol className="m-0 space-y-1 pl-5 text-sm text-[var(--color-text-2)]">{preview.next_runs.map((item) => <li key={item}>{convertToLocalizedTime(item)}</li>)}</ol>
          : <div className="text-sm text-[var(--color-text-3)]">{t('workflowOrchestration.editor.schedulePreviewPending', '完成频率设置后显示未来执行时间')}</div>}
      </Spin>
    </section>
  </section>;
}
