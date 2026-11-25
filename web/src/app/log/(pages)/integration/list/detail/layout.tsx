'use client';

import React, { useMemo } from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import { useSearchParams } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import { MenuItem } from '@/types/index';
import { isTypeScopedCollectType } from '@/app/log/(pages)/integration/receive/logExtractorLogic';
import { buildPassiveIntegrationDetailMenu } from './integrationDetailMenu';

const IntegrationDetailLayout = ({
  children
}: {
  children: React.ReactNode;
}) => {
  const searchParams = useSearchParams();
  const router = useScreenAwareRouter();
  const { t } = useTranslation();
  const pluginDisplayName = searchParams.get('display_name');
  const desc = searchParams.get('description');
  const icon = searchParams.get('icon');
  const pluginName = searchParams.get('name');
  const isK8s = useMemo(() => pluginName === 'kubernetes', [pluginName]);
  const isPassiveCollect = useMemo(
    () => isTypeScopedCollectType(pluginName),
    [pluginName]
  );

  const handleBackButtonClick = () => {
    // const params = new URLSearchParams({ id });
    // const targetUrl = `/log/integration/list?${params.toString()}`;
    router.push('/log/integration/list');
  };

  const identitySection = (
    <TopSection
      title={pluginDisplayName || '--'}
      content={desc || undefined}
      icon={
        <img
          src={`/assets/icons/${icon}.svg`}
          alt=""
          className="h-10 w-10 object-contain"
          onError={(e) => {
            (e.target as HTMLImageElement).src =
              '/assets/icons/cc-default_默认.svg';
          }}
        />
      }
    />
  );

  const customMenuItems: MenuItem[] | undefined = useMemo(() => {
    if (isK8s) {
      return [
        {
          title: t('log.integration.configuration'),
          icon: 'settings-fill',
          url: '/log/integration/list/detail/configure',
          name: 'integration_configure',
          operation: []
        }
      ];
    }
    if (!isPassiveCollect) return undefined;
    return buildPassiveIntegrationDetailMenu({
      configurationTitle: t('log.integration.configuration'),
      extractorTitle: t('log.extractor.menuTitle'),
      introductionTitle: t('log.integration.introduction')
    });
  }, [isK8s, isPassiveCollect, t]);

  return (
    <WithSideMenuLayout
      topSection={identitySection}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
      layoutType={'sideMenu'}
      customMenuItems={customMenuItems}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default IntegrationDetailLayout;
