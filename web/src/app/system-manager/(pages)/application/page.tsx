'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';
import { useClientData } from '@/context/client';
import { ClientData } from '@/types/index'

const RolePage = () => {
  const { t } = useTranslation();
  const { getAll, loading } = useClientData();
  const [dataList, setDataList] = useState<ClientData[]>([]);
  const router = useRouter();

  const loadItems = async (searchTerm = '') => {
    try {
      const data: ClientData[] = await getAll();
      const filteredData:ClientData[] = data.filter((item: ClientData) => item.name.toLowerCase().includes(searchTerm.toLowerCase()));
      setDataList(filteredData.filter((client: ClientData) => client.client_id !== 'ops-console').map((item: ClientData) => ({
        ...item,
        icon: item.client_id,
      })));
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  useEffect(() => {
    loadItems();
  }, [getAll]);

  const handleSearch = async (value: string) => {
    await loadItems(value);
  };

  const handleCardClick = (item: any) => {
    router.push(`/system-manager/application/manage?id=${item.id}&clientId=${item.client_id}`);
  };

  return (
    <div className='w-full'>
      <EntityList
        data={dataList}
        loading={loading}
        onSearch={handleSearch}
        onCardClick={handleCardClick}
      />
    </div>
  );
};

export default RolePage;
