'use client';

import React from 'react';
import { Form, Input, InputNumber, Select, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { StrategyFields } from '@/app/monitor/types/event';

const { Option } = Select;

const NO_DATA_LEVEL_OPTIONS = [
  { value: 'critical', labelKey: 'critical' },
  { value: 'error', labelKey: 'error' },
  { value: 'warning', labelKey: 'warning' }
] as const;

const FIELD_NUMBER_CLASS = 'w-[200px]';

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
  onNoDataAlertChange: (value: number | null) => void;
  onNoDataRecoveryChange: (value: number | null) => void;
  onNoDataAlertLevelChange: (val: string) => void;
  onNoDataAlertNameChange: (val: string) => void;
}

const fieldLabel = (text: string) => (
  <span className="w-[100px]">{text}</span>
);

const AlertDurationFields: React.FC<AlertDurationFieldsProps> = (props) => {
  const { t } = useTranslation();
  const noDataEnabled = props.noDataAlertLevel !== 'none';

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
          addonBefore={t('monitor.events.consecutiveCountPrefix')}
          addonAfter={t('monitor.events.consecutivePeriodUnit')}
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
          addonBefore={t('monitor.events.consecutiveCountPrefix')}
          addonAfter={t('monitor.events.consecutivePeriodUnit')}
        />
      </Form.Item>
      <Form.Item label={fieldLabel(t('monitor.events.recoveryThreshold'))}>
        <InputNumber
          className="w-[280px]"
          addonBefore={
            <Select
              allowClear
              value={props.recoveryThreshold?.method || undefined}
              popupMatchSelectWidth={false}
              style={{ width: 80 }}
              aria-label={t('monitor.events.method')}
              onChange={(method) =>
                props.onRecoveryThresholdChange?.({
                  method: method || '',
                  value: props.recoveryThreshold?.value ?? null
                })
              }
            >
              {props.allowedRecoveryMethods.map((item) => (
                <Option key={String(item.value)} value={item.value}>
                  {item.label}
                </Option>
              ))}
            </Select>
          }
          addonAfter={props.recoveryThresholdUnitLabel || undefined}
          placeholder={t('monitor.events.recoveryThresholdPlaceholder')}
          value={props.recoveryThreshold?.value ?? null}
          onChange={(value) =>
            props.onRecoveryThresholdChange?.({
              method: props.recoveryThreshold?.method || '',
              value: typeof value === 'number' ? value : null
            })
          }
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
      <Form.Item
        label={fieldLabel(t('monitor.events.noDataWindow'))}
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
      <Form.Item label={fieldLabel(t('monitor.events.noDataRecoveryWindow'))}>
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
      <Form.Item<StrategyFields>
        name="no_data_alert_name"
        label={fieldLabel(t('monitor.events.noDataAlertName'))}
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input
          style={{ width: '100%' }}
          value={noDataAlertName}
          placeholder={t('monitor.events.noDataAlertName')}
          onChange={(e) => onNoDataAlertNameChange(e.target.value)}
        />
      </Form.Item>
    </>
  );
};

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
