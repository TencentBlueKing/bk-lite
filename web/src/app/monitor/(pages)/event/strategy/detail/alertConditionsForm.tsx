import React, { useMemo } from 'react';
import { Form, Select, InputNumber, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ThresholdField } from '@/app/monitor/types';
import { StrategyFields } from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { isStringArray } from '@/app/monitor/utils/common';
import ThresholdList from './thresholdList';

const { Option } = Select;

// 无数据告警级别选项
const NO_DATA_ALERT_OPTIONS = [
  { value: 'none', labelKey: 'noTriggerNoDataAlert' },
  { value: 'critical', labelKey: 'triggerCriticalAlert' },
  { value: 'error', labelKey: 'triggerErrorAlert' },
  { value: 'warning', labelKey: 'triggerWarningAlert' }
];

interface EnumOption {
  id: number;
  name: string;
  color?: string;
}

interface AlertConditionsFormProps {
  enableAlerts: string[];
  threshold: ThresholdField[];
  calculationUnit: string | null;
  noDataAlert: number | null;
  nodataUnit: string;
  noDataRecovery: number | null;
  noDataRecoveryUnit: string;
  noDataAlertLevel: string;
  noDataAlertName: string;
  metricUnit: string | null;
  onEnableAlertsChange: (val: string[]) => void;
  onThresholdChange: (value: ThresholdField[]) => void;
  onCalculationUnitChange: (val: string) => void;
  onNodataUnitChange: (val: string) => void;
  onNoDataAlertChange: (e: number | null) => void;
  onNodataRecoveryUnitChange: (val: string) => void;
  onNoDataRecoveryChange: (e: number | null) => void;
  onNoDataAlertLevelChange: (val: string) => void;
  onNoDataAlertNameChange: (val: string) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const AlertConditionsForm: React.FC<AlertConditionsFormProps> = ({
  threshold,
  calculationUnit,
  noDataAlert,
  nodataUnit,
  noDataAlertLevel,
  noDataAlertName,
  metricUnit,
  onThresholdChange,
  onCalculationUnitChange,
  onNoDataAlertChange,
  onNoDataAlertLevelChange,
  onNoDataAlertNameChange,
  isTrap
}) => {
  const { t } = useTranslation();
  const commonContext = useCommon();
  const unitList = commonContext?.unitList || [];

  // 判断是否为枚举类型指标
  const isEnumMetric = useMemo(() => {
    return metricUnit ? isStringArray(metricUnit) : false;
  }, [metricUnit]);

  // 枚举类型的选项列表
  const enumOptions = useMemo((): EnumOption[] => {
    if (!isEnumMetric || !metricUnit) return [];
    try {
      return JSON.parse(metricUnit);
    } catch {
      return [];
    }
  }, [isEnumMetric, metricUnit]);

  // 根据指标单位过滤单位列表，只显示相同 system 的单位
  const filteredUnitOptions = useMemo(() => {
    // 枚举类型不需要单位选项
    if (isEnumMetric) return [];
    // 排除 none 和 short 单位
    const baseFilteredList = unitList.filter(
      (item) => !['none', 'short'].includes(item.unit_id)
    );
    const metricUnitItem = unitList.find((item) => item.unit_id === metricUnit);
    if (!metricUnitItem || !metricUnit) {
      return [];
    }
    const targetSystem = metricUnitItem.system;
    // 过滤出相同 system 的单位
    return baseFilteredList.filter((item) => item.system === targetSystem);
  }, [unitList, metricUnit, isEnumMetric]);

  // 验证阈值
  const validateThreshold = async () => {
    if (
      threshold.length &&
      (threshold.some((item) => {
        return !item.method;
      }) ||
        (!isEnumMetric && !calculationUnit))
    ) {
      return Promise.reject(new Error(t('monitor.events.thresholdValidate')));
    }
    return Promise.resolve();
  };

  // 是否显示无数据告警名称（选择了非"不触发"的选项时显示）
  const showNoDataAlertName = noDataAlertLevel && noDataAlertLevel !== 'none';

  return (
    <>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? null : (
            <>
              {/* 告警阈值 */}
              <Form.Item<StrategyFields>
                name="threshold"
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.alertThreshold')}
                  </span>
                }
                rules={[{ validator: validateThreshold }]}
              >
                <ThresholdList
                  data={threshold}
                  onChange={onThresholdChange}
                  calculationUnit={calculationUnit}
                  onUnitChange={onCalculationUnitChange}
                  unitOptions={filteredUnitOptions}
                  isEnumMetric={isEnumMetric}
                  enumOptions={enumOptions}
                />
              </Form.Item>

              {/* 自动恢复 */}
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
                      message: t('common.required')
                    }
                  ]}
                >
                  <InputNumber
                    className="mx-[10px] w-[100px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                {t('monitor.events.consecutivePeriods')}
              </Form.Item>

              {/* 无数据告警 */}
              <Form.Item<StrategyFields>
                name="no_data_level"
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.noDataAlertLevel')}
                  </span>
                }
              >
                <div className="flex items-center">
                  <span>{t('monitor.events.noDataAlertCondition')}</span>
                  <InputNumber
                    className="mx-[10px]"
                    style={{ width: '80px' }}
                    min={SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]}
                    max={SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]}
                    value={noDataAlert}
                    precision={0}
                    onChange={onNoDataAlertChange}
                  />
                  <span className="mr-[10px]">
                    {t('monitor.events.noDataAlertSuffix')}
                  </span>
                  <Select
                    value={noDataAlertLevel}
                    style={{ width: 180 }}
                    onChange={onNoDataAlertLevelChange}
                  >
                    {NO_DATA_ALERT_OPTIONS.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {t(`monitor.events.${item.labelKey}`)}
                      </Option>
                    ))}
                  </Select>
                </div>
              </Form.Item>

              {/* 无数据告警名称 - 条件显示 */}
              {showNoDataAlertName && (
                <Form.Item<StrategyFields>
                  name="no_data_alert_name"
                  label={
                    <span className="w-[100px]">
                      {t('monitor.events.noDataAlertName')}
                    </span>
                  }
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <Input
                    style={{ width: '100%' }}
                    value={noDataAlertName}
                    placeholder={t('monitor.events.noDataAlertName')}
                    onChange={(e) => onNoDataAlertNameChange(e.target.value)}
                    disabled
                  />
                </Form.Item>
              )}
            </>
          )
        }
      </Form.Item>
    </>
  );
};

export default AlertConditionsForm;
