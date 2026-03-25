'use client';

import React, { useMemo, useState } from 'react';
import { Button, Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ProviderModelManagement from '@/app/opspilot/components/provider/modelManagement';
import VendorBasicInfo from '@/app/opspilot/components/provider/vendorBasicInfo';
import { VENDOR_LABEL_MAP } from '@/app/opspilot/constants/provider';
import type { ModelVendor } from '@/app/opspilot/types/provider';

const ProviderDetailPage: React.FC = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const vendorId = Number(searchParams?.get('id') || '0');
  const initialTab = searchParams?.get('tab') || 'models';
  const vendorName = searchParams?.get('name') || '';
  const vendorType = searchParams?.get('vendorType') || '';
  const [vendor, setVendor] = useState<ModelVendor | null>(vendorId ? {
    id: vendorId,
    name: vendorName,
    vendor_type: (vendorType || 'other') as ModelVendor['vendor_type'],
    api_base: '',
    team: [],
  } : null);

  const activeTab = useMemo(() => (initialTab === 'basic' ? 'basic' : 'models'), [initialTab]);

  if (!vendorId) {
    return null;
  }

  return (
    <div className="w-full rounded-3xl bg-white p-5 shadow-sm lg:p-6">
      <div className="mb-2 flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-3)' }}>
        <span>供应商</span>
        <span>/</span>
        <span>{vendor?.name || vendorName}</span>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            icon={<ArrowLeftOutlined />}
            type="text"
            size="small"
            onClick={() => router.push('/opspilot/provider')}
          />
          <span className="text-[16px] font-semibold" style={{ color: 'var(--color-text-1)' }}>{vendor?.name || vendorName}</span>
        </div>
        <span className="text-xs" style={{ color: 'var(--color-text-3)' }}>
          类型: {vendor ? VENDOR_LABEL_MAP[vendor.vendor_type] : '--'}
        </span>
      </div>

      <Tabs
        className="provider-detail-tabs"
        activeKey={activeTab}
        onChange={(key) => {
          const query = new URLSearchParams({
            id: String(vendorId),
            name: vendor?.name || vendorName,
            vendorType: vendor?.vendor_type || vendorType,
            tab: key,
          });
          router.replace(`/opspilot/provider/detail?${query.toString()}`);
        }}
        items={[
          {
            key: 'basic',
            label: '基础信息',
            children: <VendorBasicInfo vendorId={vendorId} onUpdated={setVendor} />,
          },
          {
            key: 'models',
            label: '模型管理',
            children: (
              <div className="h-[calc(100vh-300px)]" style={{ minHeight: 520 }}>
                <ProviderModelManagement vendorId={vendorId} />
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ProviderDetailPage;
