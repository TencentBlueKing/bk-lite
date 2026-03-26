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
    <div className="grid w-full grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      {vendors.map((vendor) => {
        const totalModels = getModelCount(vendor);
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
            className="h-full rounded-2xl border transition-all duration-200 hover:-translate-y-0.5"
            bodyStyle={{ padding: 14, height: '100%' }}
            style={{
              borderColor: 'var(--color-border-2)',
              boxShadow: '0 4px 14px rgba(15, 23, 42, 0.04)',
            }}
            onClick={() => onOpen(vendor)}
          >
            <div className="flex min-h-22 flex-col justify-between gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2">
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-xl border bg-white"
                    style={{ borderColor: 'var(--color-border-2)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.7)' }}
                  >
                    <Image
                      src={`/app/models/${VENDOR_ICON_MAP[vendor.vendor_type]}.svg`}
                      alt={vendor.name}
                      width={20}
                      height={20}
                      className="object-contain"
                    />
                  </div>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className="truncate text-base font-semibold leading-tight" style={{ color: 'var(--color-text-1)' }}>{vendor.name}</div>
                    <div className="mt-0.5 text-[10px] font-medium" style={{ color: 'var(--color-text-3)' }}>{VENDOR_LABEL_MAP[vendor.vendor_type]}</div>
                    <Tag color="blue" className="mt-1.5 rounded-full border-0 px-2 py-0 text-[10px] font-medium leading-5">
                      {t('provider.vendor.enabledModels', undefined, { count: totalModels })}
                    </Tag>
                  </div>
                </div>

                <div onClick={(event) => event.stopPropagation()}>
                  <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-lg border bg-white hover:border-blue-400 hover:text-blue-500"
                      style={{ borderColor: 'var(--color-border-2)', color: 'var(--color-text-2)' }}
                    >
                      <MoreOutlined />
                    </button>
                  </Dropdown>
                </div>
              </div>

              <div className="flex items-center justify-end pt-0.5" onClick={(event) => event.stopPropagation()}>
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
          </Card>
        );
      })}
    </div>
  );
};

export default VendorCardGrid;
