import React from 'react';
import { Button, Form, Input, InputNumber } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';

interface RadarSettingsSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  availableFields: ResponseFieldDefinition[];
}

const buildFieldLabel = (field: ResponseFieldDefinition) => {
  return field.title && field.title !== field.key
    ? `${field.key} (${field.title})`
    : field.key;
};

export const RadarSettingsSection: React.FC<RadarSettingsSectionProps> = ({
  t,
  availableFields,
}) => {
  const hasFieldSchema = availableFields.length > 0;

  return (
    <div className="mb-6">
      <div className="font-medium mb-4">{t('dashboard.radarSettings')}</div>

      <div className="grid grid-cols-2 gap-3">
        <Form.Item label={t('dashboard.radarMin')} name={['radar', 'min']} initialValue={0}>
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          label={t('dashboard.radarMax')}
          name={['radar', 'max']}
          initialValue={100}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                const min = Number(getFieldValue(['radar', 'min']) ?? 0);
                const max = Number(value ?? 100);
                if (
                  !Number.isFinite(min) ||
                  !Number.isFinite(max) ||
                  max <= min
                ) {
                  return Promise.reject(
                    new Error(t('dashboard.radarMaxMustGreaterMin')),
                  );
                }
                return Promise.resolve();
              },
            }),
          ]}
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
      </div>

      <div className="mb-2 text-sm text-(--color-text-2)">
        {t('dashboard.radarIndicators')}
      </div>
      <Form.List name={['radar', 'indicators']}>
        {(fields, { add, remove }) => (
          <div className="flex flex-col gap-2">
            {fields.map((field, index) => (
              <div key={field.key} className="flex items-start gap-2">
                <Form.Item
                  className="mb-0 flex-1"
                  name={[field.name, 'key']}
                  rules={[{ required: true, message: t('common.inputMsg') }]}
                >
                  <Input
                    list="radar-indicator-key-options"
                    placeholder={t('dashboard.radarIndicatorKeyPlaceholder')}
                  />
                </Form.Item>
                <Form.Item className="mb-0 flex-1" name={[field.name, 'label']}>
                  <Input placeholder={t('dashboard.radarIndicatorLabelPlaceholder')} />
                </Form.Item>
                <Button
                  icon={<DeleteOutlined />}
                  onClick={() => remove(field.name)}
                  disabled={fields.length <= 1}
                  title={t('topology.delete', '删除')}
                />
                {index === fields.length - 1 ? (
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => add({ key: '', label: '' })}
                    title={t('dashboard.addField', '添加')}
                  />
                ) : null}
              </div>
            ))}
            {fields.length === 0 ? (
              <Button onClick={() => add({ key: '', label: '' })} icon={<PlusOutlined />}>
                {t('dashboard.addRadarIndicator')}
              </Button>
            ) : null}
            {hasFieldSchema ? (
              <datalist id="radar-indicator-key-options">
                {availableFields.map((field) => (
                  <option key={field.key} value={field.key}>
                    {buildFieldLabel(field)}
                  </option>
                ))}
              </datalist>
            ) : null}
          </div>
        )}
      </Form.List>
      <div className="mt-2 text-xs text-(--color-text-3)">
        {t('dashboard.radarIndicatorsHint')}
      </div>
    </div>
  );
};
