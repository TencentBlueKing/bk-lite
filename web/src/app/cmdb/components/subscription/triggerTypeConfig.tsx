import React, { useMemo } from 'react';
import { Card, Checkbox, Divider, InputNumber, Select, Space } from 'antd';
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
  relationFieldsByModel: Record<string, { id: string; name: string; type: string }[]>;
  dateFields: { id: string; name: string }[];
  triggerConfig: TriggerConfig;
  errors?: Record<string, string>;
}

const TYPES: TriggerType[] = ['attribute_change', 'relation_change', 'expiration', 'config_file'];
const ATTRIBUTE_CHANGE_EXCLUDED_FIELD_IDS = new Set([
  'inst_name',
  'organization',
  'collect_task',
  'update_time',
  'updated_time',
  'is_collect_task',
]);

interface SelectAllDropdownProps {
  menu: React.ReactElement;
  allSelected: boolean;
  noneSelected: boolean;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  selectAllText: string;
  deselectAllText: string;
}

const SelectAllDropdown: React.FC<SelectAllDropdownProps> = ({
  menu,
  allSelected,
  noneSelected,
  onSelectAll,
  onDeselectAll,
  selectAllText,
  deselectAllText,
}) => (
  <>
    <Space className="px-3 py-2">
      <a
        onClick={(e) => {
          e.preventDefault();
          if (!allSelected) onSelectAll();
        }}
        aria-disabled={allSelected}
        className={[
          'pointer-events-auto',
          allSelected ? 'cursor-not-allowed text-[var(--color-text-4)]' : 'cursor-pointer',
        ].join(' ')}
      >
        {selectAllText}
      </a>
      <Divider type="vertical" className="m-0" />
      <a
        onClick={(e) => {
          e.preventDefault();
          if (!noneSelected) onDeselectAll();
        }}
        aria-disabled={noneSelected}
        className={[
          'pointer-events-auto',
          noneSelected ? 'cursor-not-allowed text-[var(--color-text-4)]' : 'cursor-pointer',
        ].join(' ')}
      >
        {deselectAllText}
      </a>
    </Space>
    <Divider className="mb-1 mt-0" />
    {menu}
  </>
);

const TriggerTypeConfigComp: React.FC<TriggerTypeConfigProps> = ({
  value,
  onChange,
  modelFields,
  relatedModels,
  relationFieldsByModel,
  dateFields,
  triggerConfig,
  errors = {},
}) => {
  const { t } = useTranslation();
  const attributeChangeDefaultFields = useMemo(
    () => modelFields
      .filter((field) => !ATTRIBUTE_CHANGE_EXCLUDED_FIELD_IDS.has(field.id))
      .map((field) => field.id),
    [modelFields]
  );
  const attributeChangeAllFields = useMemo(
    () => modelFields.map((field) => field.id),
    [modelFields]
  );
  const normalizeRelationChangeModels = useMemo(() => {
    const relationChange = triggerConfig.relation_change;
    const byNewShape = relationChange?.related_models;
    if (Array.isArray(byNewShape) && byNewShape.length > 0) {
      return byNewShape
        .filter((item) => !!item?.related_model)
        .map((item) => ({
          related_model: item.related_model,
          fields: Array.isArray(item.fields) ? item.fields : [],
        }));
    }
    if (relationChange?.related_model) {
      return [{
        related_model: relationChange.related_model,
        fields: Array.isArray(relationChange.fields) ? relationChange.fields : [],
      }];
    }
    return [];
  }, [triggerConfig.relation_change]);

  const titleMap = {
    attribute_change: t('subscription.triggerTypeAttributeChange'),
    relation_change: t('subscription.triggerTypeRelationChange'),
    expiration: t('subscription.triggerTypeExpiration'),
    config_file: t('subscription.triggerTypeConfigFile'),
  } as const;

  const descMap = {
    attribute_change: t('subscription.attributeChangeDesc'),
    relation_change: t('subscription.relationChangeDesc'),
    expiration: t('subscription.expirationDesc'),
    config_file: t('subscription.configFileDesc'),
  } as const;

  const toggleType = (type: TriggerType) => {
    const checked = value.includes(type);
    const nextTypes = checked ? value.filter((v) => v !== type) : [...value, type];
    const nextConfig: TriggerConfig = { ...triggerConfig };
    if (!checked) {
      if (type === 'attribute_change' && !nextConfig.attribute_change) {
        nextConfig.attribute_change = { fields: attributeChangeDefaultFields };
      }
      if (type === 'relation_change' && !nextConfig.relation_change) {
        nextConfig.relation_change = { related_models: [] };
      }
      if (type === 'expiration' && !nextConfig.expiration) {
        nextConfig.expiration = { time_field: '', days_before: 1 };
      }
      if (type === 'config_file' && !nextConfig.config_file) {
        nextConfig.config_file = {};
      }
    }
    onChange(nextTypes, nextConfig);
  };

  const updateConfig = (patch: Partial<TriggerConfig>) => {
    onChange(value, { ...triggerConfig, ...patch });
  };

  const renderConfigContent = (type: TriggerType) => {
    if (!value.includes(type)) return null;

    if (type === 'attribute_change') {
      const hasError = !!errors['attribute_change.fields'];
      const selectedFields = triggerConfig.attribute_change?.fields || [];
      const allSelected = attributeChangeAllFields.length > 0
        && selectedFields.length === attributeChangeAllFields.length;
      const noneSelected = selectedFields.length === 0;

      return (
        <div className="mb-3">
          <label className="mb-1.5 block text-[13px] leading-5 text-[var(--color-text-1)]">{t('subscription.watchFields')}</label>
          <Select
            mode="multiple"
            className="w-full"
            status={hasError ? 'error' : undefined}
            placeholder={t('common.selectMsg')}
            value={selectedFields}
            onChange={(fields) => updateConfig({ attribute_change: { fields } })}
            options={modelFields.map((i) => ({ label: i.name, value: i.id }))}
            maxTagCount="responsive"
            popupRender={(menu) => (
              <SelectAllDropdown
                menu={menu}
                allSelected={allSelected}
                noneSelected={noneSelected}
                onSelectAll={() => updateConfig({ attribute_change: { fields: attributeChangeAllFields } })}
                onDeselectAll={() => updateConfig({ attribute_change: { fields: [] } })}
                selectAllText={t('common.selectAll')}
                deselectAllText={t('common.deselectAll')}
              />
            )}
          />
          {hasError && (
            <div className="mt-1 text-xs text-[var(--color-fail)]">
              {errors['attribute_change.fields']}
            </div>
          )}
        </div>
      );
    }

    if (type === 'relation_change') {
      const hasModelError = !!errors['relation_change.related_models'];
      const selectedModelIds = normalizeRelationChangeModels.map((item) => item.related_model);

      return (
        <div>
          <div className="mb-3">
            <label className="mb-1.5 block text-[13px] leading-5 text-[var(--color-text-1)]">{t('subscription.relatedModel')}</label>
            <Select
              mode="multiple"
              className="w-full"
              status={hasModelError ? 'error' : undefined}
              placeholder={t('common.selectMsg')}
              value={selectedModelIds}
              onChange={(related_model_ids: string[]) => {
                const existingMap = new Map(
                  normalizeRelationChangeModels.map((item) => [item.related_model, item.fields])
                );
                const nextRelatedModels = related_model_ids.map((related_model) => ({
                  related_model,
                  fields: existingMap.get(related_model) || [],
                }));
                updateConfig({
                  relation_change: {
                    related_models: nextRelatedModels,
                    related_model: nextRelatedModels[0]?.related_model,
                    fields: nextRelatedModels[0]?.fields || [],
                  },
                });
              }}
              options={relatedModels.map((i) => ({ label: i.name, value: i.id }))}
              maxTagCount="responsive"
            />
            {hasModelError && (
              <div className="mt-1 text-xs text-[var(--color-fail)]">
                {errors['relation_change.related_models']}
              </div>
            )}
          </div>
          {normalizeRelationChangeModels.map((item) => {
            const relationFields = relationFieldsByModel[item.related_model] || [];
            const relationChangeAllFields = relationFields.map((field) => field.id);
            const selectedFields = item.fields || [];
            const allSelected = relationChangeAllFields.length > 0
              && selectedFields.length === relationChangeAllFields.length;
            const noneSelected = selectedFields.length === 0;
            const modelFieldsError = errors[`relation_change.related_models.${item.related_model}.fields`];

            return (
              <div key={item.related_model} className="mb-3">
                <div className="mb-2 text-xs text-[var(--color-text-3)]">
                  {relatedModels.find((m) => m.id === item.related_model)?.name || item.related_model}
                </div>
                <div className="mb-0">
                  <label className="mb-1.5 block text-[13px] leading-5 text-[var(--color-text-1)]">{t('subscription.relatedFields')}</label>
                  <Select
                    mode="multiple"
                    className="w-full"
                    status={modelFieldsError ? 'error' : undefined}
                    placeholder={t('common.selectMsg')}
                    value={selectedFields}
                    onChange={(fields) => {
                      const nextRelatedModels = normalizeRelationChangeModels.map((current) => (
                        current.related_model === item.related_model
                          ? { ...current, fields }
                          : current
                      ));
                      updateConfig({
                        relation_change: {
                          related_models: nextRelatedModels,
                          related_model: nextRelatedModels[0]?.related_model,
                          fields: nextRelatedModels[0]?.fields || [],
                        },
                      });
                    }}
                    options={relationFields.map((field) => ({ label: field.name, value: field.id }))}
                    maxTagCount="responsive"
                    popupRender={(menu) => (
                      <SelectAllDropdown
                        menu={menu}
                        allSelected={allSelected}
                        noneSelected={noneSelected}
                        onSelectAll={() => {
                          const nextRelatedModels = normalizeRelationChangeModels.map((current) => (
                            current.related_model === item.related_model
                              ? { ...current, fields: relationChangeAllFields }
                              : current
                          ));
                          updateConfig({
                            relation_change: {
                              related_models: nextRelatedModels,
                              related_model: nextRelatedModels[0]?.related_model,
                              fields: nextRelatedModels[0]?.fields || [],
                            },
                          });
                        }}
                        onDeselectAll={() => {
                          const nextRelatedModels = normalizeRelationChangeModels.map((current) => (
                            current.related_model === item.related_model
                              ? { ...current, fields: [] }
                              : current
                          ));
                          updateConfig({
                            relation_change: {
                              related_models: nextRelatedModels,
                              related_model: nextRelatedModels[0]?.related_model,
                              fields: nextRelatedModels[0]?.fields || [],
                            },
                          });
                        }}
                        selectAllText={t('common.selectAll')}
                        deselectAllText={t('common.deselectAll')}
                      />
                    )}
                  />
                  {modelFieldsError && (
                    <div className="mt-1 text-xs text-[var(--color-fail)]">
                      {modelFieldsError}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    if (type === 'expiration') {
      const hasError = !!errors['expiration.time_field'];
      return (
        <div>
          <div className="mb-3">
            <label className="mb-1.5 block text-[13px] leading-5 text-[var(--color-text-1)]">{t('subscription.timeField')}</label>
            <Select
              className="w-full"
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
              <div className="mt-1 text-xs text-[var(--color-fail)]">
                {errors['expiration.time_field']}
              </div>
            )}
          </div>
          <div className="mb-0">
            <label className="mb-1.5 block text-[13px] leading-5 text-[var(--color-text-1)]">{t('subscription.daysBefore')}</label>
            <InputNumber
              min={1}
              className="w-full"
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
      );
    }

    if (type === 'config_file') {
      return null;
    }

    return null;
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2">
        {TYPES.map((type) => {
          const checked = value.includes(type);
          return (
            <Card
              key={type}
              size="small"
              className="min-w-0 cursor-pointer"
              style={{
                borderColor: checked ? 'var(--ant-color-primary)' : undefined,
              }}
              styles={{ body: { padding: '8px 12px' } }}
              onClick={() => toggleType(type)}
            >
              <div className="flex items-start gap-2">
                <Checkbox
                  checked={checked}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => toggleType(type)}
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1">
                  <div className="mb-1 font-medium leading-5">{titleMap[type]}</div>
                  <div className="text-xs leading-[18px] text-[var(--color-text-4)]">{descMap[type]}</div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {value.map((type) => {
        const content = renderConfigContent(type);
        if (!content) {
          return null;
        }

        return (
          <div key={type} className="rounded-md bg-[var(--color-fill-1)] p-3">
            <div className="mb-3 text-[13px] font-medium text-[var(--color-text-1)]">
              {titleMap[type]}{t('subscription.config')}
            </div>
            {content}
          </div>
        );
      })}
    </div>
  );
};

export default TriggerTypeConfigComp;
