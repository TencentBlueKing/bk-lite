'use client';
import React, { useMemo } from 'react';
import SubLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import { usePathname } from 'next/navigation';
import Icon from '@/components/icon/index';
import { useSearchParams } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';

const Collectorintro = () => {
  const searchParams = useSearchParams();
  const name = searchParams.get('displayName');
  return (
    <div className="flex h-[58px] flex-col items-center justify-center">
      <Icon
        type="yunquyu"
        className="h-16 w-16"
        style={{ height: '36px', width: '36px' }}
      ></Icon>
      <h1 className="text-center">{name}</h1>
    </div>
  );
};

const CollectorLayout = ({
  children
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const router = useScreenAwareRouter();
  const { t } = useTranslation();
  const customMenuItems = useMemo(() => {
    const menuItems = [
      {
        title: t('node-manager.cloudregion.pageConfig.node.title'),
        url: '/node-manager/cloudregion/node',
        icon: 'jiedianguanli',
        name: 'cloud_region_node'
      },
      {
        title: t('node-manager.cloudregion.pageConfig.environment.title'),
        url: '/node-manager/cloudregion/environment',
        icon: 'windows',
        name: 'cloud_region_environment'
      },
      {
        title: t('node-manager.cloudregion.pageConfig.variable.title'),
        url: '/node-manager/cloudregion/variable',
        icon: 'bianliang',
        name: 'cloud_region_variable'
      }
    ];
    return menuItems as any;
  }, [t]);

  const pageConfig = {
    node: {
      title: t('node-manager.cloudregion.pageConfig.node.title'),
      description: t('node-manager.cloudregion.pageConfig.node.description')
    },
    environment: {
      title: t('node-manager.cloudregion.pageConfig.environment.title'),
      description: t(
        'node-manager.cloudregion.pageConfig.environment.description'
      )
    },
    variable: {
      title: t('node-manager.cloudregion.pageConfig.variable.title'),
      description: t('node-manager.cloudregion.pageConfig.variable.description')
    }
  };
  const Topsection = () => {
    const pathname = usePathname();
    const getPageKey = () => {
      return pathname.split('/')[3] || 'node';
    };
    const pageKey = getPageKey() as keyof typeof pageConfig;
    const { title, description } = pageConfig[pageKey] || pageConfig.node;
    return <TopSection title={title} content={description} />;
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <SubLayout
        topSection={<Topsection></Topsection>}
        showBackButton={true}
        intro={<Collectorintro></Collectorintro>}
        customMenuItems={customMenuItems}
        onBackButtonClick={() => {
          router.push('/node-manager/cloudregion/');
        }}
      >
        {children}
      </SubLayout>
    </div>
  );
};
export default CollectorLayout;
