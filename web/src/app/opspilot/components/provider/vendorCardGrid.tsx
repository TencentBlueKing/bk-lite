import React, { useState } from 'react';
import { Card, Dropdown, Empty, Modal, Switch, Tag, Tooltip, message } from 'antd';
import Image from 'next/image';
import { MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { VENDOR_ICON_MAP, VENDOR_LABEL_MAP } from '@/app/opspilot/constants/provider';
import type { ModelVendor } from '@/app/opspilot/types/provider';
import { useProviderApi } from '@/app/opspilot/api/provider';
import { ProviderGridSkeleton } from '@/app/opspilot/components/provider/skeleton';

interface VendorCardGridProps {
  vendors: ModelVendor[];
  loading: boolean;
  onOpen: (vendor: ModelVendor) => void;
  onEdit: (vendor: ModelVendor) => void;
  onDelete: (vendor: ModelVendor) => void;
  onChange: (vendor: ModelVendor) => void;
}

const VendorCardGrid: React.FC<VendorCardGridProps> = ({
  vendors,
  loading,
  onOpen,
  onEdit,
  onDelete,
  onChange,
}) => {
  const { t } = useTranslation();
  const { patchVendor } = useProviderApi();
  const [switchLoadingId, setSwitchLoadingId] = useState<number | null>(null);

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

    return `${VENDOR_LABEL_MAP[vendor.vendor_type]} API 服务`;
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
    return <ProviderGridSkeleton />;
  }

  if (!loading && vendors.length === 0) {
    return <Empty description={t('provider.vendor.empty')} />;
  }

  return (
    <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      {vendors.map((vendor) => {
        const totalModels = getModelCount(vendor);
        const description = getVendorDescription(vendor);
        const menuItems = [
          {
            key: 'edit',
            label: <span className="block w-full" onClick={() => onEdit(vendor)}>{t('common.edit')}</span>,
          },
          {
            key: 'delete',
            danger: true,
            label: <span className="block w-full" onClick={() => showDeleteConfirm(vendor)}>{t('common.delete')}</span>,
          },
        ];

        return (
          <Card
            key={vendor.id}
            hoverable
            className="group h-full overflow-hidden rounded-[26px] border-0 transition-all duration-300 hover:-translate-y-1"
            bodyStyle={{ padding: 0, height: '100%' }}
            style={{
              background: '#ffffff',
              boxShadow: '0 14px 28px rgba(148, 163, 184, 0.10)',
              border: '1px solid rgba(191, 219, 254, 0.7)',
            }}
            onClick={() => onOpen(vendor)}
          >
            <div className="relative flex min-h-42 flex-col overflow-hidden px-5 py-4.5">
              <div
                className="pointer-events-none absolute inset-x-0 top-0 h-22"
                style={{
                  background: 'linear-gradient(180deg, rgba(239, 246, 255, 0.95) 0%, rgba(255, 255, 255, 0) 100%)',
                }}
              />
              <div
                className="pointer-events-none absolute -top-8 left-8 h-18 w-32 rounded-full blur-3xl"
                style={{ background: 'rgba(147, 197, 253, 0.18)' }}
              />

              <div className="relative flex flex-1 flex-col">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <div
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] border shadow-[0_10px_24px_rgba(96,165,250,0.14)] backdrop-blur-sm"
                      style={{
                        borderColor: 'rgba(191, 219, 254, 0.9)',
                        background: 'linear-gradient(145deg, rgba(248, 251, 255, 0.96) 0%, rgba(231, 242, 255, 0.92) 100%)',
                      }}
                    >
                      <Image
                        src={`/app/models/${VENDOR_ICON_MAP[vendor.vendor_type]}.svg`}
                        alt={vendor.name}
                        width={24}
                        height={24}
                        className="object-contain"
                      />
                    </div>

                    <div className="min-w-0 flex-1 pt-0.5">
                      <div className="truncate text-[16px] font-semibold leading-tight tracking-[-0.01em] text-(--color-text-1)">{vendor.name}</div>
                      <Tag
                        color="blue"
                        className="mt-1 rounded-full border-blue-200/80 bg-white/90 px-2 py-0 text-[10px] font-medium leading-4.5 text-blue-600 shadow-[0_4px_10px_rgba(59,130,246,0.08)]"
                      >
                        {VENDOR_LABEL_MAP[vendor.vendor_type]}
                      </Tag>
                    </div>
                  </div>

                  <div className="opacity-0 transition-opacity duration-200 group-hover:opacity-100" onClick={(event) => event.stopPropagation()}>
                    <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
                      <button
                        type="button"
                        className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200/80 bg-white/88 text-(--color-text-2) shadow-[0_4px_12px_rgba(148,163,184,0.08)] backdrop-blur-sm hover:border-blue-200 hover:text-blue-500"
                      >
                        <MoreOutlined />
                      </button>
                    </Dropdown>
                  </div>
                </div>

                <div className="mt-3 line-clamp-1 text-[13px] leading-6 text-slate-600">
                  {description}
                </div>

                <div className="mt-auto pt-3">
                  <div className="h-px w-full bg-linear-to-r from-sky-100 via-slate-100 to-transparent" />
                  <div className="flex items-center justify-between gap-4 pt-3.5">
                    <div className="text-[12px] font-medium tracking-[0.01em] text-slate-600">{totalModels} 个模型</div>

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
            </div>
          </Card>
        );
      })}
    </div>
  );
};

export default VendorCardGrid;
