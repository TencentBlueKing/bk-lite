import React from 'react';
import { Form, Select, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ThresholdField } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useScheduleList } from '@/app/monitor/hooks/event';
import { useLevelList } from '@/app/monitor/hooks';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import SelectCards from './selectCard';
import ThresholdList from './thresholdList';

const { Option } = Select;

interface AlertConditionsFormProps {
  enableAlerts: string[];
  threshold: ThresholdField[];
  noDataAlert: number | null;
  nodataUnit: string;
  noDataRecovery: number | null;
  noDataRecoveryUnit: string;
  onEnableAlertsChange: (val: string[]) => void;
  onThresholdChange: (value: ThresholdField[]) => void;
  onNodataUnitChange: (val: string) => void;
  onNoDataAlertChange: (e: number | null) => void;
  onNodataRecoveryUnitChange: (val: string) => void;
  onNoDataRecoveryChange: (e: number | null) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const AlertConditionsForm: React.FC<AlertConditionsFormProps> = ({
  enableAlerts,
  threshold,
  noDataAlert,
  nodataUnit,
  noDataRecovery,
  noDataRecoveryUnit,
  onEnableAlertsChange,
  onThresholdChange,
  onNodataUnitChange,
  onNoDataAlertChange,
  onNodataRecoveryUnitChange,
  onNoDataRecoveryChange,
  isTrap,
}) => {
  const { t } = useTranslation();
  // 在组件内部引入hooks，减少props传递
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();

  // 验证函数移到组件内部
  const validateThreshold = async () => {
    if (!enableAlerts.length) {
      return Promise.reject(new Error(t('common.required')));
    }
    if (
      enableAlerts.includes('threshold') &&
      threshold.length &&
      (threshold.some((item) => {
        return !item.method;
      }) ||
        !threshold.some((item) => {
          return !!item.value || item.value === 0;
        }))
    ) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
    }
    return Promise.resolve();
  };

  const validateNoDataAlert = async () => {
    if (!noDataAlert || !nodataUnit) {
      return Promise.reject(new Error(t('common.required')));
    }
    return Promise.resolve();
  };

  const validateNoDataRecoveryAlert = async () => {
    if (!noDataRecovery || !noDataRecoveryUnit) {
      return Promise.reject(new Error(t('common.required')));
    }
    return Promise.resolve();
  };

  return (
    <>
      <Form.Item<StrategyFields>
        name="threshold"
        label={
          <span className="w-[100px]">{t('monitor.events.algorithm')}</span>
        }
        rules={[{ validator: validateThreshold, required: true }]}
      >
        <SelectCards
          value={enableAlerts}
          onChange={onEnableAlertsChange}
          data={[
            {
              value: 'threshold',
              icon: 'yuzhiguanli',
              title: t('monitor.events.threshold'),
              content: t('monitor.events.setThreshold'),
            },
            {
              value: 'no_data',
              icon: 'dengdeng',
              title: t('monitor.events.nodata'),
              content: t('monitor.events.setThreshold'),
            },
          ]}
        />
        <div>
          {enableAlerts.includes('threshold') && (
            <ThresholdList data={threshold} onChange={onThresholdChange} />
          )}
        </div>
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? null : (
            <>
              {enableAlerts.includes('threshold') && (
                <Form.Item<StrategyFields>
                  label={
                    <span className="w-[100px]">
                      {t('monitor.events.recovery')}
                    </span>
                  }
                >
                  {t('monitor.events.recoveryCondition')}
                  <Form.Item
                    name="recovery_condition"
                    noStyle
                    rules={[
                      {
                        required: false,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <InputNumber
                      className="mx-[10px] w-[100px]"
                      min={1}
                      precision={0}
                    />
                  </Form.Item>
                  {t('monitor.events.consecutivePeriods')}
                  <div className="text-[var(--color-text-3)] mt-[10px]">
                    {t('monitor.events.setRecovery')}
                  </div>
                </Form.Item>
              )}
              {enableAlerts.includes('no_data') && (
                <>
                  <Form.Item<StrategyFields>
                    name="no_data_period"
                    label={
                      <span className="w-[100px]">
                        {t('monitor.integrations.condition')}
                      </span>
                    }
                    rules={[
                      {
                        required: true,
                        validator: validateNoDataAlert,
                      },
                    ]}
                  >
                    <div className="flex items-center">
                      {t('monitor.events.reportedFor')}
                      <InputNumber
                        className="mx-[10px]"
                        min={SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]}
                        max={SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]}
                        value={noDataAlert}
                        precision={0}
                        addonAfter={
                          <Select
                            value={nodataUnit}
                            style={{ width: 120 }}
                            onChange={onNodataUnitChange}
                          >
                            {SCHEDULE_LIST.map((item) => (
                              <Option key={item.value} value={item.value}>
                                {item.label}
                              </Option>
                            ))}
                          </Select>
                        }
                        onChange={onNoDataAlertChange}
                      />
                      {t('monitor.events.nodataPeriods')}
                    </div>
                  </Form.Item>
                  <Form.Item<StrategyFields>
                    name="no_data_level"
                    label={
                      <span className="w-[100px]">
                        {t('monitor.events.alarmLevel')}
                      </span>
                    }
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Select
                      style={{
                        width: '100px',
                      }}
                      placeholder={t('monitor.events.level')}
                    >
                      {LEVEL_LIST.map((item) => (
                        <Option value={item.value} key={item.value}>
                          {item.label}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                  <Form.Item<StrategyFields>
                    name="no_data_recovery_period"
                    label={
                      <span className="w-[100px]">
                        {t('monitor.events.noDataRecovery')}
                      </span>
                    }
                    rules={[
                      {
                        required: true,
                        validator: validateNoDataRecoveryAlert,
                      },
                    ]}
                  >
                    <div className="flex items-center">
                      {t('monitor.events.nodataRecoverCondition')}
                      <InputNumber
                        className="mx-[10px]"
                        min={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Min`]}
                        max={SCHEDULE_UNIT_MAP[`${noDataRecoveryUnit}Max`]}
                        value={noDataRecovery}
                        precision={0}
                        addonAfter={
                          <Select
                            value={noDataRecoveryUnit}
                            style={{ width: 120 }}
                            onChange={onNodataRecoveryUnitChange}
                          >
                            {SCHEDULE_LIST.map((item) => (
                              <Option key={item.value} value={item.value}>
                                {item.label}
                              </Option>
                            ))}
                          </Select>
                        }
                        onChange={onNoDataRecoveryChange}
                      />
                      {t('monitor.events.nodataRecover')}
                    </div>
                  </Form.Item>
                </>
              )}
            </>
          )
        }
      </Form.Item>
    </>
  );
};

export default AlertConditionsForm;
