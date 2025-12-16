import React from 'react';
import { Form, Input, Button, Select, InputNumber } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { StrategyFields, SourceFeild } from '@/app/monitor/types/event';
import { useScheduleList } from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';

const { Option } = Select;

interface BasicInfoFormProps {
  source: SourceFeild;
  unit: string;
  onOpenInstModal: () => void;
  onUnitChange: (val: string) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const BasicInfoForm: React.FC<BasicInfoFormProps> = ({
  source,
  unit,
  onOpenInstModal,
  onUnitChange,
  isTrap,
}) => {
  const { t } = useTranslation();
  const SCHEDULE_LIST = useScheduleList();

  const validateAssets = async () => {
    if (!source.values.length) {
      return Promise.reject(new Error(t('monitor.assetValidate')));
    }
    return Promise.resolve();
  };

  return (
    <>
      <Form.Item<StrategyFields>
        label={
          <span className="w-[100px]">{t('monitor.events.strategyName')}</span>
        }
        name="name"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <Input
          placeholder={t('monitor.events.strategyName')}
          className="w-[800px]"
        />
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">{t('monitor.events.alertName')}</span>
        }
      >
        <Form.Item
          name="alert_name"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required'),
            },
          ]}
        >
          <Input
            placeholder={t('monitor.events.alertName')}
            className="w-[800px]"
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('monitor.events.alertNameTitle')}
        </div>
      </Form.Item>
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('monitor.group')}</span>}
        name="organizations"
        rules={[{ required: true, message: t('common.required') }]}
      >
        <GroupTreeSelector
          style={{
            width: '800px',
            marginRight: '8px',
          }}
          placeholder={t('common.group')}
        />
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.collect_type !== currentValues.collect_type
        }
      >
        {({ getFieldValue }) =>
          isTrap(getFieldValue) ? null : (
            <Form.Item<StrategyFields>
              label={
                <span className="w-[100px]">{t('monitor.events.target')}</span>
              }
              name="source"
              rules={[{ required: true, validator: validateAssets }]}
            >
              <div>
                <div className="flex">
                  {t('common.select')}
                  <span className="text-[var(--color-primary)] px-[4px]">
                    {source.values.length}
                  </span>
                  {t('monitor.assets')}
                  <Button
                    className="ml-[10px]"
                    icon={<PlusOutlined />}
                    size="small"
                    onClick={onOpenInstModal}
                  ></Button>
                </div>
                <div className="text-[var(--color-text-3)] mt-[10px]">
                  {t('monitor.events.setAssets')}
                </div>
              </div>
            </Form.Item>
          )
        }
      </Form.Item>
      <Form.Item<StrategyFields>
        required
        label={
          <span className="w-[100px]">
            {t('monitor.events.testingFrequency')}
          </span>
        }
      >
        <Form.Item
          name="schedule"
          noStyle
          rules={[
            {
              required: true,
              message: t('common.required'),
            },
          ]}
        >
          <InputNumber
            min={SCHEDULE_UNIT_MAP[`${unit}Min`]}
            max={SCHEDULE_UNIT_MAP[`${unit}Max`]}
            precision={0}
            addonAfter={
              <Select
                value={unit}
                style={{ width: 120 }}
                onChange={onUnitChange}
              >
                {SCHEDULE_LIST.map((item) => (
                  <Option key={item.value} value={item.value}>
                    {item.label}
                  </Option>
                ))}
              </Select>
            }
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('monitor.events.setFrequency')}
        </div>
      </Form.Item>
    </>
  );
};

export default BasicInfoForm;
