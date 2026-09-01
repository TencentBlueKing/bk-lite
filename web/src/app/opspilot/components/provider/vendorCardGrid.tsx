'use client';

import React, { useState } from 'react';
import { Menu, Modal, message } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { VENDOR_ICON_MAP, VENDOR_LABEL_MAP } from '@/app/opspilot/constants/provider';
import type { ModelVendor } from '@/app/opspilot/types/provider';
import { useProviderApi } from '@/app/opspilot/api/provider';
import { ProviderGridSkeleton } from '@/app/opspilot/components/provider/skeleton';
import UnifiedOpsCard from '@/app/opspilot/components/unified-ops-card';
import { formatRelativeTime, pickEntityTimestamp } from '@/app/opspilot/utils/relativeTime';

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
    return <ProviderGridSkeleton />;
  }

  if (!loading && vendors.length === 0) {
    return <CompactEmptyState description={t('provider.vendor.empty')} />;
  }

  return (
    <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
      {vendors.map((vendor) => {
        const totalModels = getModelCount(vendor);
        const description = getVendorDescription(vendor);
        const menu = (
          <Menu>
            <Menu.Item key={`edit-${vendor.id}`}>
              <span className="block" onClick={() => onEdit(vendor)}>
                {t('common.edit')}
              </span>
            </Menu.Item>
            <Menu.Item key={`delete-${vendor.id}`}>
              <span className="block" onClick={() => showDeleteConfirm(vendor)}>
                {t('common.delete')}
              </span>
            </Menu.Item>
          </Menu>
        );

        return (
          <UnifiedOpsCard
            key={vendor.id}
            name={vendor.name}
            description={description}
            vendorIcon={VENDOR_ICON_MAP[vendor.vendor_type]}
            updatedAt={formatRelativeTime(pickEntityTimestamp(vendor), t) || undefined}
            meta={[VENDOR_LABEL_MAP[vendor.vendor_type]].filter(Boolean)}
            footer="provider"
            modelCount={totalModels}
            enabled={vendor.enabled}
            switchLoading={switchLoadingId === vendor.id}
            menuOverlay={menu}
            onClick={() => onOpen(vendor)}
            onEnabledChange={(checked) => handleToggleEnabled(vendor, checked)}
          />
        );
      })}
    </div>
  );
};

export default VendorCardGrid;
