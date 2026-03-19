import React from 'react';
import { Card, Checkbox, InputNumber, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  TriggerConfig,
  TriggerType,
} from '@/app/cmdb/types/subscription';

interface TriggerTypeConfigProps {
  value: TriggerType[];
  onChange: (types: TriggerType[], config: TriggerConfig) => void;
  modelFields: { id: string; name: string; type: string }[];
  relatedModels: { id: string; name: string }[];
  relationFields: { id: string; name: string; type: string }[];
  dateFields: { id: string; name: string }[];
  triggerConfig: TriggerConfig;
  errors?: Record<string, string>;
}

const TYPES: TriggerType[] = ['attribute_change', 'relation_change', 'expiration'];

const TriggerTypeConfigComp: React.FC<TriggerTypeConfigProps> = ({
  value,
  onChange,
  modelFields,
  relatedModels,
  relationFields,
  dateFields,
  triggerConfig,
  errors = {},
}) => {
  const { t } = useTranslation();

  const titleMap = {
    attribute_change: t('subscription.triggerTypeAttributeChange'),
    relation_change: t('subscription.triggerTypeRelationChange'),
    expiration: t('subscription.triggerTypeExpiration'),
  } as const;

  const descMap = {
    attribute_change: t('subscription.attributeChangeDesc'),
    relation_change: t('subscription.relationChangeDesc'),
    expiration: t('subscription.expirationDesc'),
  } as const;

  const toggleType = (type: TriggerType) => {
    const checked = value.includes(type);
    const nextTypes = checked ? value.filter((v) => v !== type) : [...value, type];
    const nextConfig: TriggerConfig = { ...triggerConfig };
    if (!checked) {
      if (type === 'attribute_change' && !nextConfig.attribute_change) {
        nextConfig.attribute_change = { fields: [] };
      }
      if (type === 'relation_change' && !nextConfig.relation_change) {
        nextConfig.relation_change = { related_model: '', fields: [] };
      }
      if (type === 'expiration' && !nextConfig.expiration) {
        nextConfig.expiration = { time_field: '', days_before: 1 };
      }
    }
    onChange(nextTypes, nextConfig);
  };

  const updateConfig = (patch: Partial<TriggerConfig>) => {
    onChange(value, { ...triggerConfig, ...patch });
  };

  const renderConfigContent = (type: TriggerType) => {
    if (!value.includes(type)) return null;

    const rowStyle = { display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 };
    const labelStyle: React.CSSProperties = { fontSize: 13, color: '#333', width: 56, flexShrink: 0, lineHeight: '32px' };
    const fieldStyle = { flex: 1 };

    if (type === 'attribute_change') {
      const hasError = !!errors['attribute_change.fields'];
      return (
        <div style={rowStyle}>
          <label style={labelStyle}>{t('subscription.watchFields')}</label>
          <div style={fieldStyle}>
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              status={hasError ? 'error' : undefined}
              placeholder={t('common.selectMsg')}
              value={triggerConfig.attribute_change?.fields || []}
              onChange={(fields) => updateConfig({ attribute_change: { fields } })}
              options={modelFields.map((i) => ({ label: i.name, value: i.id }))}
            />
            {hasError && (
              <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
                {errors['attribute_change.fields']}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (type === 'relation_change') {
      const hasModelError = !!errors['relation_change.related_model'];
      const hasFieldsError = !!errors['relation_change.fields'];
      return (
        <div>
          <div style={rowStyle}>
            <label style={labelStyle}>{t('subscription.relatedModel')}</label>
            <div style={fieldStyle}>
              <Select
                style={{ width: '100%' }}
                status={hasModelError ? 'error' : undefined}
                placeholder={t('common.selectMsg')}
                value={triggerConfig.relation_change?.related_model || undefined}
                onChange={(related_model) =>
                  updateConfig({
                    relation_change: {
                      related_model,
                      fields: triggerConfig.relation_change?.fields || [],
                    },
                  })
                }
                options={relatedModels.map((i) => ({ label: i.name, value: i.id }))}
              />
              {hasModelError && (
                <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
                  {errors['relation_change.related_model']}
                </div>
              )}
            </div>
          </div>
          <div style={{ ...rowStyle, marginBottom: 0 }}>
            <label style={labelStyle}>{t('subscription.relatedFields')}</label>
            <div style={fieldStyle}>
              <Select
                mode="multiple"
                style={{ width: '100%' }}
                status={hasFieldsError ? 'error' : undefined}
                placeholder={t('common.selectMsg')}
                value={triggerConfig.relation_change?.fields || []}
                onChange={(fields) =>
                  updateConfig({
                    relation_change: {
                      related_model: triggerConfig.relation_change?.related_model || '',
                      fields,
                    },
                  })
                }
                options={relationFields.map((i) => ({ label: i.name, value: i.id }))}
              />
              {hasFieldsError && (
                <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
                  {errors['relation_change.fields']}
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    if (type === 'expiration') {
      const hasError = !!errors['expiration.time_field'];
      return (
        <div>
          <div style={rowStyle}>
            <label style={labelStyle}>{t('subscription.timeField')}</label>
            <div style={fieldStyle}>
              <Select
                style={{ width: '100%' }}
                status={hasError ? 'error' : undefined}
                placeholder={t('common.selectMsg')}
                value={triggerConfig.expiration?.time_field || undefined}
                onChange={(time_field) =>
                  updateConfig({
                    expiration: {
                      time_field,
                      days_before: triggerConfig.expiration?.days_before || 1,
                    },
                  })
                }
                options={dateFields.map((i) => ({ label: i.name, value: i.id }))}
              />
              {hasError && (
                <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
                  {errors['expiration.time_field']}
                </div>
              )}
            </div>
          </div>
          <div style={{ ...rowStyle, marginBottom: 0 }}>
            <label style={labelStyle}>{t('subscription.daysBefore')}</label>
            <div style={fieldStyle}>
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                value={triggerConfig.expiration?.days_before || 1}
                onChange={(days_before) =>
                  updateConfig({
                    expiration: {
                      time_field: triggerConfig.expiration?.time_field || '',
                      days_before: Number(days_before || 1),
                    },
                  })
                }
                addonAfter={t('subscription.naturalDays')}
              />
            </div>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {TYPES.map((type) => {
          const checked = value.includes(type);
          return (
            <Card
              key={type}
              size="small"
              style={{
                width: 180,
                borderColor: checked ? 'var(--ant-color-primary)' : undefined,
                cursor: 'pointer',
              }}
              styles={{ body: { padding: '8px 12px' } }}
              onClick={() => toggleType(type)}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <Checkbox
                  checked={checked}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => toggleType(type)}
                  style={{ marginTop: 2 }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 500, marginBottom: 4 }}>{titleMap[type]}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>{descMap[type]}</div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {value.map((type) => (
        <div key={type} style={{ padding: '12px', background: '#fafafa', borderRadius: 6 }}>
          <div style={{ fontSize: 13, color: '#333', marginBottom: 12, fontWeight: 500 }}>
            {titleMap[type]}{t('subscription.config')}
          </div>
          {renderConfigContent(type)}
        </div>
      ))}
    </div>
  );
};

export default TriggerTypeConfigComp;
