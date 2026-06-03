'use client';

import React, { useEffect, useState, createContext, useContext, useMemo } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { useMemoryApi, MemorySpace } from '@/app/opspilot/api/memory';
import { MenuItem } from '@/types/index';

interface MemoryContextType {
  space: MemorySpace | null;
  loading: boolean;
  refreshSpace: () => void;
}

const MemoryContext = createContext<MemoryContextType>({
  space: null,
  loading: false,
  refreshSpace: () => {},
});

export const useMemoryContext = () => useContext(MemoryContext);

const LayoutContent = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { fetchMemorySpace } = useMemoryApi();
  const idStr = searchParams.get('id');
  const id = idStr ? parseInt(idStr, 10) : 0;

  const [space, setSpace] = useState<MemorySpace | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshSpace = () => {
    if (id) {
      setLoading(true);
      fetchMemorySpace(id).then(res => {
        setSpace(res);
      }).catch(e => {
        console.error(e);
      }).finally(() => {
        setLoading(false);
      });
    }
  };

  useEffect(() => {
    refreshSpace();
  }, [id]);

  const handleBackButtonClick = () => {
    router.push('/opspilot/memory');
  };

  const intro = (
    <OnelineEllipsisIntro name={space?.name || '-'} desc={space?.introduction || '-'} />
  );

  const customMenuItems: MenuItem[] = useMemo(() => [
    {
      title: t('memory.config'),
      url: '/opspilot/memory/detail/config',
      icon: 'shezhi',
      name: 'memory_detail_config',
      operation: [],
    },
    {
      title: t('memory.memories'),
      url: '/opspilot/memory/detail/memories',
      icon: 'shujuguanli',
      name: 'memory_detail_memories',
      operation: [],
    },
  ], [t]);

  return (
    <MemoryContext.Provider value={{ space, loading, refreshSpace }}>
      <WithSideMenuLayout
        topSection={<TopSection title={t('memory.title')} content={t('memory.summaryDesc')} />}
        intro={intro}
        showBackButton={true}
        onBackButtonClick={handleBackButtonClick}
        customMenuItems={customMenuItems}
      >
        {children}
      </WithSideMenuLayout>
    </MemoryContext.Provider>
  );
};

export default function MemoryDetailLayout({ children }: { children: React.ReactNode }) {
  return <LayoutContent>{children}</LayoutContent>;
}
