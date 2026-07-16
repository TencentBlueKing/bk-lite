'use client';

import React from 'react';
import { Button, Popconfirm, Switch } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import OpspilotProviderEmptyState from '@/components/opspilot-provider-empty-state';
import { useTranslation } from '@/utils/i18n';
import type { Model, ProviderResourceType } from '@/app/opspilot/types/provider';

export interface OpspilotProviderModelSectionStyle {
  topGlow: string;
  panelGlow: string;
  headerBg: string;
  sectionBg: string;
  tableBg: string;
  borderColor: string;
  shadow: string;
}

export interface OpspilotProviderModelSectionProps {
  type: ProviderResourceType;
  title: string;
  count: number;
  models: Model[];
  switchingKey: string | null;
  style: OpspilotProviderModelSectionStyle;
  getModelIdentifier: (model: Model, type: ProviderResourceType) => string;
  getTeamText: (model: Model) => string;
  onAdd: (type: ProviderResourceType) => void;
  onEdit: (type: ProviderResourceType, model: Model) => void;
  onDelete: (type: ProviderResourceType, model: Model) => void;
  onToggleEnabled: (type: ProviderResourceType, model: Model, enabled: boolean) => void;
}

const OpspilotProviderModelSection: React.FC<OpspilotProviderModelSectionProps> = ({
  type,
  title,
  count,
  models,
  switchingKey,
  style,
  getModelIdentifier,
  getTeamText,
  onAdd,
  onEdit,
  onDelete,
  onToggleEnabled,
}) => {
  const { t } = useTranslation();

  return (
    <section
      className="relative flex flex-col overflow-hidden rounded-2xl border"
      style={{
        borderColor: style.borderColor,
        background: style.sectionBg,
        boxShadow: style.shadow,
        height: 'calc((100vh - 360px) / 2)',
        minHeight: 240,
      }}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-24"
        style={{ background: style.topGlow }}
      />
      <div
        className="pointer-events-none absolute -top-7 left-10 h-20 w-36 rounded-full blur-3xl"
        style={{ background: style.panelGlow }}
      />

      <div
        className="relative flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: 'rgba(191, 219, 254, 0.55)', background: style.headerBg }}
      >
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-1)' }}>{title}</h3>
          <span className="text-xs" style={{ color: 'var(--color-text-3)' }}>
            {t('provider.model.totalCount', undefined, { count })}
          </span>
        </div>
        <Button type="primary" ghost size="small" icon={<PlusOutlined />} onClick={() => onAdd(type)}>
          {t('provider.model.add')}
        </Button>
      </div>

      {models.length === 0 ? (
        <div className="relative flex flex-1 items-center justify-center px-4 py-8">
          <OpspilotProviderEmptyState variant="model" />
        </div>
      ) : (
        <div className="relative flex-1 overflow-auto backdrop-blur-[2px]" style={{ background: style.tableBg }}>
          <div className="min-w-160">
            <div
              className="grid grid-cols-[1.2fr_1.4fr_1fr_88px_100px] border-b px-4 py-3 text-xs font-medium"
              style={{ borderColor: 'var(--color-border-2)', color: 'var(--color-text-3)' }}
            >
              <span>{t('provider.model.modelName')}</span>
              <span>{t('provider.model.modelId')}</span>
              <span>{t('provider.model.availableGroups')}</span>
              <span>{t('provider.model.enabled')}</span>
              <span>{t('common.edit')}</span>
            </div>

            {models.map((model) => (
              <div
                key={`${type}-${model.id}`}
                className="grid grid-cols-[1.2fr_1.4fr_1fr_88px_100px] items-center border-b px-4 py-3 text-sm"
                style={{ borderColor: 'var(--color-border-2)', color: 'var(--color-text-2)' }}
              >
                <span className="truncate pr-3">{model.name || '--'}</span>
                <span className="truncate pr-3">{getModelIdentifier(model, type) || '--'}</span>
                <span className="truncate pr-3">{getTeamText(model)}</span>
                <span>
                  <Switch
                    size="small"
                    checked={Boolean(model.enabled)}
                    loading={switchingKey === `${type}-${model.id}`}
                    disabled={switchingKey === `${type}-${model.id}`}
                    onChange={(checked) => onToggleEnabled(type, model, checked)}
                  />
                </span>
                <span className="flex items-center gap-1">
                  <Button type="text" size="small" icon={<EditOutlined />} onClick={() => onEdit(type, model)} />
                  <Popconfirm
                    title={t('provider.model.deleteConfirmTitle')}
                    okText={t('common.confirm')}
                    cancelText={t('common.cancel')}
                    okButtonProps={{ danger: true }}
                    onConfirm={() => onDelete(type, model)}
                  >
                    <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

export default OpspilotProviderModelSection;
