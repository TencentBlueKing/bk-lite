import React, { useImperativeHandle, forwardRef, useRef } from 'react';
import { Form, Input, Button, Select, InputNumber, InputRef } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import { StrategyFields, SourceFeild } from '@/app/monitor/types/event';
import { useScheduleList } from '@/app/monitor/hooks/event';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import { insertAlertNameVariableAtCursor } from './strategyDetailUtils';

const { Option } = Select;

export interface BasicInfoFormRef {
  insertVariable: (variable: string) => void;
}

interface BasicInfoFormProps {
  source: SourceFeild;
  unit: string;
  onOpenInstModal: () => void;
  onUnitChange: (val: string) => void;
  isTrap: (getFieldValue: any) => boolean;
}

const BasicInfoForm = forwardRef<BasicInfoFormRef, BasicInfoFormProps>(
  ({ source, unit, onOpenInstModal, onUnitChange, isTrap }, ref) => {
    const form = Form.useFormInstance<StrategyFields>();
    const alertNameInputRef = useRef<InputRef>(null);
    const alertNameSelectionRef = useRef<{ start: number; end: number } | null>(
      null
    );

    const saveAlertNameSelection = (target?: EventTarget | null) => {
      const input =
        (target instanceof HTMLInputElement ? target : null) ||
        alertNameInputRef.current?.input ||
        null;
      if (!input) return;
      alertNameSelectionRef.current = {
        start: input.selectionStart ?? 0,
        end: input.selectionEnd ?? 0
      };
    };

    useImperativeHandle(ref, () => ({
      insertVariable: (variable: string) => {
        const input = alertNameInputRef.current?.input;
        const currentValue = String(form.getFieldValue('alert_name') || '');
        const isFocused = !!input && document.activeElement === input;
        const selection = isFocused
          ? {
              start: input.selectionStart ?? currentValue.length,
              end: input.selectionEnd ?? currentValue.length
            }
          : alertNameSelectionRef.current;
        const { value, cursor } = insertAlertNameVariableAtCursor(
          currentValue,
          variable,
          selection?.start,
          selection?.end
        );
        form.setFieldsValue({ alert_name: value });
        alertNameSelectionRef.current = { start: cursor, end: cursor };
        requestAnimationFrame(() => {
          alertNameInputRef.current?.focus();
          alertNameInputRef.current?.setSelectionRange(cursor, cursor);
        });
      }
    }));
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
            <span className="w-[100px]">
              {t('monitor.events.strategyName')}
            </span>
          }
          name="name"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Input
            placeholder={t('monitor.events.strategyName')}
            className="w-full"
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
                message: t('common.required')
              }
            ]}
          >
            <Input
              ref={alertNameInputRef}
              placeholder={t('monitor.events.alertName')}
              className="w-full"
              onSelect={(event) => saveAlertNameSelection(event.target)}
              onKeyUp={(event) => saveAlertNameSelection(event.target)}
              onClick={(event) => saveAlertNameSelection(event.target)}
            />
          </Form.Item>
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {t('monitor.events.alertNameTitle')}
          </div>
        </Form.Item>
        <Form.Item<StrategyFields>
          required
          label={<span className="w-[100px]">{t('monitor.group')}</span>}
        >
          <Form.Item<StrategyFields>
            name="organizations"
            noStyle
            rules={[
              {
                required: true,
                message: t('common.required')
              }
            ]}
          >
            <GroupTreeSelector
              style={{
                width: '100%',
                marginRight: '8px'
              }}
              placeholder={t('common.group')}
            />
          </Form.Item>
          <div className="text-[var(--color-text-3)] mt-[10px]">
            {t('monitor.events.setGroup')}
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
              <Form.Item<StrategyFields>
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.target')}
                  </span>
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
                    {source.type === 'instance'
                      ? t('monitor.assets')
                      : t('monitor.group')}
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
          label={
            <span className="w-[100px]">
              {t('monitor.events.testingFrequency')}
            </span>
          }
          name="schedule"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <InputNumber
            className="w-full"
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
      </>
    );
  }
);

BasicInfoForm.displayName = 'BasicInfoForm';

export default BasicInfoForm;
