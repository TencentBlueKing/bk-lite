'use client';
import SubLayout from '@/components/sub-layout';
import React, { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import type { ControllerCardProps } from '@/app/node-manager/types/controller';

const ControllerLayout = ({ children }: { children: React.ReactNode }) => {
  const router = useRouter();
  const { t } = useTranslation();
  const pathname = usePathname();
  const [detaildata, setDetaildata] = useState<ControllerCardProps>({
    id: '',
    name: '',
    system: [],
    introduction: '',
    icon: '',
  });

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const info = {
      id: searchParams.get('id') || '',
      name: searchParams.get('name') || '',
      system: [searchParams.get('system') || ''],
      introduction: searchParams.get('introduction') || '',
      icon: searchParams.get('icon') || 'caijiqizongshu',
    };
    setDetaildata(info);
  }, [pathname]);

  //顶部的组件
  const Topsection = () => {
    return (
      <div className="flex flex-col h-[90px] p-4 overflow-hidden">
        <h1 className="text-lg">{t('node-manager.packetManage.title')}</h1>
        <p className="text-sm overflow-hidden w-full min-w-[1000px] mt-[8px]">
          {detaildata.introduction}
        </p>
      </div>
    );
  };

  const CollectorIntro = () => {
    return (
      <div className="h-[58px] flex flex-col justify-items-center">
        <div className="flex justify-center mb-[8px]">
          <Icon
            type={detaildata.icon}
            style={{ height: '34px', width: '34px' }}
          ></Icon>
        </div>
        <div className="flex justify-center">
          <div>{detaildata.name}</div>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full">
      <SubLayout
        layoutType={'sideMenu'}
        topSection={<Topsection></Topsection>}
        showBackButton={true}
        intro={<CollectorIntro></CollectorIntro>}
        onBackButtonClick={() => {
          router.back();
        }}
      >
        {children}
      </SubLayout>
    </div>
  );
};

export default ControllerLayout;
