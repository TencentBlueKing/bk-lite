'use client';
import React from 'react';
import SubLayout from '@/components/sub-layout';
import { useTranslation } from '@/utils/i18n';
import { usePathname } from 'next/navigation';
import Icon from '@/components/icon/index';
import { useRouter } from 'next/navigation';

const Collectorintro = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const name = searchParams.get('name');
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
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  const router = useRouter();
  const { t } = useTranslation();
  const Topsection = () => {
    const pathname = usePathname();
    const getTitle = () => {
      const temp = pathname.split('/')[3];
      return t(`common.${temp}`);
    };
    return (
      <div className="flex flex-col h-[90px] p-4 overflow-hidden">
        <h1 className="text-lg">{getTitle()}</h1>
        <p className="text-sm overflow-hidden w-full min-w-[1000px] mt-[8px]">
          {t('common.topdes')}
        </p>
      </div>
    );
  };
  return (
    <div>
      <SubLayout
        topSection={<Topsection></Topsection>}
        showBackButton={true}
        intro={<Collectorintro></Collectorintro>}
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
