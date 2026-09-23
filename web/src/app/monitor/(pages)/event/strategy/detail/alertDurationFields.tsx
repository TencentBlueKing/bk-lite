'use client';

import React from 'react';
import { Form, Input, InputNumber, Select, Space, Switch, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { StrategyFields } from '@/app/monitor/types/event';
import { isPodMonitorObject } from '@/app/monitor/utils/monitorObject';

const { Option } = Select;

const NO_DATA_LEVEL_OPTIONS = [
  { value: 'critical', labelKey: 'critical' },
  { value: 'error', labelKey: 'error' },
  { value: 'warning', labelKey: 'warning' }
] as const;

const FIELD_NUMBER_CLASS = 'w-[200px]';

export const STRATEGY_CONDITION_LABEL_WIDTH = 100;
export const STRATEGY_CONDITION_LABEL_CLASS =
  'inline-block w-[100px] whitespace-nowrap';

interface RecoveryMethodOption {
  value?: string | number;
  label?: React.ReactNode;
}

interface AlertDurationFieldsProps {
  recoveryThreshold?: { method?: string; value?: number | null };
  onRecoveryThresholdChange?: (val: {
    method?: string;
    value?: number | null;
  }) => void;
  allowedRecoveryMethods: RecoveryMethodOption[];
  recoveryThresholdUnitLabel: string;
  noDataAlert: number | null;
  nodataUnit: string;
  noDataRecovery: number | null;
  noDataRecoveryUnit: string;
  noDataAlertLevel: string;
  noDataAlertName: string;
  functionDelayTip?: string;
  monitorName?: string;
  onNoDataAlertChange: (value: number | null) => void;
  onNoDataRecoveryChange: (value: number | null) => void;
  onNoDataAlertLevelChange: (val: string) => void;
  onNoDataAlertNameChange: (val: string) => void;
}

const fieldLabel = (text: string) => (
  <span className={STRATEGY_CONDITION_LABEL_CLASS}>{text}</span>
);

export const strategyConditionLabelWithTip = (text: string, tip: string) => (
  <span className="inline-flex w-[100px] items-center justify-end gap-1 whitespace-nowrap">
    <span>{text}</span>
    <Tooltip title={tip} overlayInnerStyle={{ whiteSpace: 'pre-line' }}>
      <QuestionCircleOutlined className="text-[var(--color-text-3)]" />
    </Tooltip>
  </span>
);

const AlertDurationFields: React.FC<AlertDurationFieldsProps> = (props) => {
  const { t } = useTranslation();
  const noDataEnabled = props.noDataAlertLevel !== 'none';
  const triggerCount = Form.useWatch('trigger_count');
  const recoveryCount = Form.useWatch('recovery_condition');
  const consecutivePrefix = t('monitor.events.consecutiveCountPrefix');

  return (
    <>
      <Form.Item<StrategyFields>
        name="trigger_count"
        label={fieldLabel(t('monitor.events.triggerCondition'))}
        rules={[{ required: true, message: t('common.required') }]}
      >
        <InputNumber
          min={1}
          precision={0}
          className={FIELD_NUMBER_CLASS}
          addonBefore={consecutivePrefix || undefined}
          addonAfter={consecutivePeriodUnit(t, triggerCount)}
        />
      </Form.Item>
      <Form.Item<StrategyFields>
        name="recovery_condition"
        label={fieldLabel(t('monitor.events.recovery'))}
      >
        <InputNumber
          min={1}
          precision={0}
          className={FIELD_NUMBER_CLASS}
          addonBefore={consecutivePrefix || undefined}
          addonAfter={consecutivePeriodUnit(t, recoveryCount)}
        />
      </Form.Item>
      <Form.Item label={fieldLabel(t('monitor.events.recoveryThreshold'))}>
        <RecoveryThresholdInput
          recoveryThreshold={props.recoveryThreshold}
          allowedRecoveryMethods={props.allowedRecoveryMethods}
          recoveryThresholdUnitLabel={props.recoveryThresholdUnitLabel}
          placeholder={t('monitor.events.recoveryThresholdPlaceholder')}
          methodAriaLabel={t('monitor.events.method')}
          onRecoveryThresholdChange={props.onRecoveryThresholdChange}
        />
      </Form.Item>
      <Form.Item label={fieldLabel(t('monitor.events.noDataAlertLevel'))}>
        <Switch
          checked={noDataEnabled}
          onChange={(checked) => setNoDataEnabled(props, checked)}
        />
        <div className="mt-[10px] text-[var(--color-text-3)]">
          {t('monitor.events.noDataAlertTip')}
        </div>
        {isPodMonitorObject(props.monitorName) ? (
          <div className="mt-[8px] text-[12px] leading-[20px] text-[var(--color-text-3)]">
            {t('monitor.events.noDataPodTip')}
          </div>
        ) : null}
      </Form.Item>
      {noDataEnabled ? <NoDataDetailFields {...props} /> : null}
    </>
  );
};

const NoDataDetailFields: React.FC<AlertDurationFieldsProps> = ({
  noDataAlert,
  nodataUnit,
  noDataRecovery,
  noDataRecoveryUnit,
  noDataAlertLevel,
  noDataAlertName,
  functionDelayTip,
  onNoDataAlertChange,
  onNoDataRecoveryChange,
  onNoDataAlertLevelChange,
  onNoDataAlertNameChange
}) => {
  const { t } = useTranslation();
  return (
    <>
      <Form.Item<StrategyFields>
        name="no_data_alert_name"
        label={fieldLabel(t('monitor.events.alertName'))}
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input
          style={{ width: '100%' }}
          value={noDataAlertName}
          placeholder={t('monitor.events.noDataAlertName')}
          onChange={(e) => onNoDataAlertNameChange(e.target.value)}
        />
      </Form.Item>
      <Form.Item
        label={strategyConditionLabelWithTip(
          t('monitor.events.noDataWindow'),
          t('monitor.events.noDataWindowTitle')
        )}
        extra={
          functionDelayTip ? (
            <span className="text-[12px] text-[var(--color-text-3)]">
              {functionDelayTip}
            </span>
          ) : undefined
        }
      >
        <InputNumber
          className={FIELD_NUMBER_CLASS}
          min={SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]}
          max={SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]}
          value={noDataAlert}
          precision={0}
          addonAfter={t('monitor.events.minutes')}
          onChange={onNoDataAlertChange}
        />
      </Form.Item>
      <Form.Item label={fieldLabel(t('monitor.events.level'))}>
        <Select
          value={noDataAlertLevel}
          popupMatchSelectWidth={false}
          style={{ width: 200 }}
          onChange={onNoDataAlertLevelChange}
        >
          {NO_DATA_LEVEL_OPTIONS.map((item) => (
            <Option key={item.value} value={item.value}>
              {t(`monitor.events.${item.labelKey}`)}
            </Option>
          ))}
        </Select>
      </Form.Item>
      <Form.Item
        label={strategyConditionLabelWithTip(
          t('monitor.events.noDataRecoveryWindow'),
          t('monitor.events.noDataRecoveryWindowTitle')
        )}
      >
        <InputNumber
          className={FIELD_NUMBER_CLASS}
          min={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Min`]}
          max={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Max`]}
          value={noDataRecovery}
          precision={0}
          addonAfter={t('monitor.events.minutes')}
          onChange={onNoDataRecoveryChange}
        />
      </Form.Item>
    </>
  );
};

function RecoveryThresholdInput({
  recoveryThreshold,
  allowedRecoveryMethods,
  recoveryThresholdUnitLabel,
  placeholder,
  methodAriaLabel,
  onRecoveryThresholdChange
}: {
  recoveryThreshold?: { method?: string; value?: number | null };
  allowedRecoveryMethods: RecoveryMethodOption[];
  recoveryThresholdUnitLabel: string;
  placeholder: string;
  methodAriaLabel: string;
  onRecoveryThresholdChange?: (val: {
    method?: string;
    value?: number | null;
  }) => void;
}) {
  const displayedMethod =
    recoveryThreshold?.method ||
    String(allowedRecoveryMethods[0]?.value || '>');

  const commit = (next: {
    method?: string;
    value?: number | null;
  }) => {
    onRecoveryThresholdChange?.({
      method: next.method || displayedMethod,
      value: next.value ?? null
    });
  };

  return (
    <Space.Compact>
      <Select
        value={displayedMethod}
        popupMatchSelectWidth={false}
        style={{ width: 72 }}
        aria-label={methodAriaLabel}
        disabled={!allowedRecoveryMethods.length}
        onChange={(method) =>
          commit({
            method: String(method),
            value: recoveryThreshold?.value ?? null
          })
        }
      >
        {allowedRecoveryMethods.map((item) => (
          <Option key={String(item.value)} value={item.value}>
            {item.label}
          </Option>
        ))}
      </Select>
      <InputNumber
        className={FIELD_NUMBER_CLASS}
        placeholder={placeholder}
        value={recoveryThreshold?.value ?? null}
        addonAfter={recoveryThresholdUnitLabel || undefined}
        onChange={(value) =>
          commit({
            method: displayedMethod,
            value: typeof value === 'number' ? value : null
          })
        }
      />
    </Space.Compact>
  );
}

function consecutivePeriodUnit(
  t: (id: string) => string,
  count: number | string | null | undefined
) {
  return Number(count) === 1
    ? t('monitor.events.consecutivePeriodUnitOne')
    : t('monitor.events.consecutivePeriodUnit');
}

function setNoDataEnabled(props: AlertDurationFieldsProps, enabled: boolean) {
  if (enabled) {
    props.onNoDataAlertLevelChange(
      props.noDataAlertLevel !== 'none' ? props.noDataAlertLevel : 'warning'
    );
    if (props.noDataAlert == null) {
      props.onNoDataAlertChange(5);
    }
    if (props.noDataRecovery == null) {
      props.onNoDataRecoveryChange(props.noDataAlert ?? 5);
    }
    return;
  }
  props.onNoDataAlertLevelChange('none');
}

export default AlertDurationFields;
