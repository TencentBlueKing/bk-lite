import React, { useState } from 'react';
import { Modal, Switch, Tooltip, message } from 'antd';
import Image from 'next/image';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import SemanticBadge from '@/components/semantic-badge';
import OpspilotProviderEmptyState from '@/app/opspilot/components/opspilot-provider-empty-state';
import { OpspilotProviderGridSkeleton } from '@/app/opspilot/components/opspilot-provider-skeletons';
import { useTranslation } from '@/utils/i18n';
import { VENDOR_ICON_MAP, VENDOR_LABEL_MAP } from '@/app/opspilot/constants/provider';
import type { ModelVendor } from '@/app/opspilot/types/provider';
import { useProviderApi } from '@/app/opspilot/api/provider';
import { useTheme } from '@/context/theme';

export interface OpspilotProviderVendorGridProps {
  vendors: ModelVendor[];
  loading: boolean;
  onOpen: (vendor: ModelVendor) => void;
  onEdit: (vendor: ModelVendor) => void;
  onDelete: (vendor: ModelVendor) => void;
  onChange: (vendor: ModelVendor) => void;
}

const OpspilotProviderVendorGrid: React.FC<OpspilotProviderVendorGridProps> = ({
  vendors,
  loading,
  onOpen,
  onEdit,
  onDelete,
  onChange,
}) => {
  const { t } = useTranslation();
  const { themeName } = useTheme();
  const { patchVendor } = useProviderApi();
  const [switchLoadingId, setSwitchLoadingId] = useState<number | null>(null);
  const isDark = themeName === 'dark';

  const getModelCount = (vendor: ModelVendor) => {
    if (typeof vendor.model_count === 'number') {
      return vendor.model_count;
    }

    return [
      vendor.llm_model_count,
      vendor.embed_model_count,
      vendor.rerank_model_count,
      vendor.ocr_model_count,
    ].reduce((total, count) => total + (count || 0), 0);
  };

  const getVendorDescription = (vendor: ModelVendor) => {
    if (vendor.description?.trim()) {
      return vendor.description.trim();
    }

    return '';
  };

  const showDeleteConfirm = (vendor: ModelVendor) => {
    Modal.confirm({
      title: t('provider.vendor.deleteConfirm'),
      content: t('provider.vendor.deleteConfirmContent', undefined, { name: vendor.name }),
      onOk: async () => onDelete(vendor),
    });
  };

  const handleToggleEnabled = async (vendor: ModelVendor, enabled: boolean) => {
    setSwitchLoadingId(vendor.id);
    try {
      await patchVendor(vendor.id, { enabled });
      message.success(t('common.updateSuccess'));
      onChange({ ...vendor, enabled });
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setSwitchLoadingId(null);
    }
  };

  if (loading) {
    return <OpspilotProviderGridSkeleton />;
  }

  if (!loading && vendors.length === 0) {
    return <OpspilotProviderEmptyState variant="vendor" />;
  }

  return (
    <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      {vendors.map((vendor) => {
        const totalModels = getModelCount(vendor);
        const description = getVendorDescription(vendor);

        return (
          <div
            key={vendor.id}
            className="group relative flex min-h-42 cursor-pointer flex-col overflow-hidden rounded-xl bg-(--color-bg) p-4 shadow-md transition-all duration-300 hover:-translate-y-0.5"
            onClick={() => onOpen(vendor)}
          >
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-22"
              style={{
                background: isDark
                  ? 'linear-gradient(180deg, rgba(21, 90, 239, 0.14) 0%, transparent 100%)'
                  : 'linear-gradient(180deg, rgba(239, 246, 255, 0.95) 0%, transparent 100%)',
              }}
            />

            <div className="relative flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-(--color-fill-1)">
                  <Image
                    src={`/app/models/${VENDOR_ICON_MAP[vendor.vendor_type]}.svg`}
                    alt={vendor.name}
                    width={24}
                    height={24}
                    className="object-contain"
                  />
                </div>

                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="truncate text-sm font-semibold text-(--color-text-1)">{vendor.name}</div>
                  <div className="mt-1">
                    <SemanticBadge
                      label={VENDOR_LABEL_MAP[vendor.vendor_type]}
                      textColor="var(--color-primary)"
                      backgroundColor="color-mix(in srgb, var(--color-primary) 12%, transparent)"
                    />
                  </div>
                </div>
              </div>

              <div
                className="flex items-center gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                onClick={(event) => event.stopPropagation()}
              >
                <button
                  type="button"
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-(--color-text-3) transition-all duration-200 hover:bg-(--color-fill-1) hover:text-(--color-primary)"
                  onClick={() => onEdit(vendor)}
                >
                  <EditOutlined />
                </button>

                <button
                  type="button"
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-transparent text-(--color-text-3) transition-all duration-200 hover:bg-(--color-fill-1) hover:text-(--color-primary)"
                  onClick={() => showDeleteConfirm(vendor)}
                >
                  <DeleteOutlined />
                </button>
              </div>
            </div>

            <div className="mt-3 h-5 text-xs text-(--color-text-3)">
              {description && (
                <span className="line-clamp-1">{description}</span>
              )}
            </div>

            <div className="mt-auto pt-4">
              <div className="flex items-center justify-between gap-4">
                <div className="text-xs text-(--color-text-4)">{totalModels} 个模型</div>

                <div onClick={(event) => event.stopPropagation()}>
                  <Tooltip title={vendor.enabled ? t('common.enable') : t('common.disable')}>
                    <Switch
                      size="small"
                      checked={vendor.enabled}
                      loading={switchLoadingId === vendor.id}
                      onChange={(checked) => handleToggleEnabled(vendor, checked)}
                    />
                  </Tooltip>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default OpspilotProviderVendorGrid;
