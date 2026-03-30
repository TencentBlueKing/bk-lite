'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Input, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useProviderApi } from '@/app/opspilot/api/provider';
import VendorCardGrid from '@/app/opspilot/components/provider/vendorCardGrid';
import VendorModal from '@/app/opspilot/components/provider/vendorModal';
import { useTranslation } from '@/utils/i18n';
import type { ModelVendor, ModelVendorPayload } from '@/app/opspilot/types/provider';
import { VENDOR_LABEL_MAP } from '@/app/opspilot/constants/provider';

interface VendorModalSubmitValues extends Omit<ModelVendorPayload, 'api_key'> {
  api_key?: string;
}

const { Search } = Input;

const ProviderPage: React.FC = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { fetchVendors, createVendor, updateVendor, deleteVendor } = useProviderApi();

  const [vendors, setVendors] = useState<ModelVendor[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalMode, setModalMode] = useState<'add' | 'edit'>('add');
  const [editingVendor, setEditingVendor] = useState<ModelVendor | null>(null);

  const loadVendors = async (search = '') => {
    setLoading(true);
    try {
      const data = await fetchVendors(search ? { search } : undefined);
      setVendors(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load vendors:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVendors();
  }, []);

  const displayedVendors = useMemo(() => {
    const keyword = searchValue.trim().toLowerCase();
    if (!keyword) {
      return vendors;
    }

    return vendors.filter((vendor) => {
      const vendorTypeLabel = VENDOR_LABEL_MAP[vendor.vendor_type]?.toLowerCase() || '';
      return vendor.name.toLowerCase().includes(keyword) || vendorTypeLabel.includes(keyword);
    });
  }, [searchValue, vendors]);

  const openAddModal = () => {
    setModalMode('add');
    setEditingVendor(null);
    setIsModalVisible(true);
  };

  const openEditModal = (vendor: ModelVendor) => {
    setModalMode('edit');
    setEditingVendor(vendor);
    setIsModalVisible(true);
  };

  const handleVendorChange = (vendor: ModelVendor) => {
    setVendors((prev) => prev.map((item) => (item.id === vendor.id ? vendor : item)));
    if (editingVendor?.id === vendor.id) {
      setEditingVendor(vendor);
    }
  };

  const handleModalSubmit = async (values: VendorModalSubmitValues) => {
    setModalLoading(true);
    try {
      if (modalMode === 'add') {
        await createVendor(values as ModelVendorPayload);
        message.success(t('common.saveSuccess'));
      } else if (editingVendor) {
        await updateVendor(editingVendor.id, values);
        message.success(t('common.updateSuccess'));
      }

      setIsModalVisible(false);
      await loadVendors(searchValue.trim());
    } catch {
      message.error(modalMode === 'add' ? t('common.saveFailed') : t('common.updateFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleDelete = async (vendor: ModelVendor) => {
    try {
      await deleteVendor(vendor.id);
      message.success(t('common.delSuccess'));
      await loadVendors(searchValue.trim());
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleOpenDetail = (vendor: ModelVendor) => {
    const query = new URLSearchParams({
      id: String(vendor.id),
      name: vendor.name,
      vendorType: vendor.vendor_type,
      tab: 'models',
    });
    router.push(`/opspilot/provider/detail?${query.toString()}`);
  };

  const handleSearch = () => {
    loadVendors(searchValue.trim());
  };

  const handleRefresh = () => {
    loadVendors(searchValue.trim());
  };

  return (
    <div className="min-h-full w-full rounded-3xl">
      <div className="mb-4 flex w-full flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="text-[16px] font-semibold leading-tight" style={{ color: 'var(--color-text-1)' }}>
            {t('provider.vendor.pageTitle')}
          </div>
          <div className="mt-1.5 text-[11px]" style={{ color: 'var(--color-text-3)' }}>
            {t('provider.vendor.pageDescription')}
          </div>
        </div>

        <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:ml-auto lg:w-auto">
          <Search
            allowClear
            enterButton
            value={searchValue}
            placeholder={t('provider.vendor.searchPlaceholder')}
            className="w-full sm:w-72 lg:w-80"
            onChange={(event) => setSearchValue(event.target.value)}
            onSearch={handleSearch}
          />
          <Button icon={<ReloadOutlined />} onClick={handleRefresh} aria-label={t('common.refresh')} />
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
            {t('provider.vendor.addButton')}
          </Button>
        </div>
      </div>

      <VendorCardGrid
        vendors={displayedVendors}
        loading={loading}
        onOpen={handleOpenDetail}
        onEdit={openEditModal}
        onDelete={handleDelete}
        onChange={handleVendorChange}
      />

      <VendorModal
        visible={isModalVisible}
        mode={modalMode}
        vendor={editingVendor}
        confirmLoading={modalLoading}
        onOk={handleModalSubmit}
        onCancel={() => setIsModalVisible(false)}
      />
    </div>
  );
};

export default ProviderPage;
