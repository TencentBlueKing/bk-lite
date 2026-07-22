'use client';

import React, { useMemo } from 'react';
import { WithSideMenuLayout } from '@/components/layout';
import SideMenu from './side-menu';
import { usePathname, useSearchParams } from 'next/navigation';
import { usePermissions } from '@/context/permissions';
import { isConfigFileSupportedModel } from '@/app/cmdb/constants/configFile';
import { getClosestAncestorMenuItems } from '@/utils/menuHelpers';

export interface AssetDataLayoutProps {
  intro?: React.ReactNode;
  showBackButton?: boolean;
  children: React.ReactNode;
  topSection?: React.ReactNode;
  showProgress?: boolean;
  showSideMenu?: boolean;
  layoutType?: 'sideMenu' | 'segmented';
  taskProgressComponent?: React.ReactNode;
  pagePathName?: string;
  relationData?: Array<{
    title: string;
    children: Array<{
      text: string;
      value?: number;
      model_asst_id: string;
    }>;
  }>;
  onBackButtonClick?: () => void;
}

const AssetDataLayout: React.FC<AssetDataLayoutProps> = ({
  intro,
  showBackButton,
  children,
  topSection,
  showProgress,
  showSideMenu = true,
  layoutType = 'sideMenu',
  taskProgressComponent,
  pagePathName,
  onBackButtonClick,
}) => {
  const curRouterName = usePathname();
  const searchParams = useSearchParams();
  const pathname = pagePathName ?? curRouterName;
  const modelId = searchParams.get('model_id');
  const { menus } = usePermissions();

  const menuItems = useMemo(() => {
    return getClosestAncestorMenuItems(menus, pathname)?.filter(menu => (
      !menu.isNotMenuItem
      && (menu.name !== 'asset_config_files' || isConfigFileSupportedModel(modelId))
    ));
  }, [menus, modelId, pathname]);

  return (
    <WithSideMenuLayout
      intro={intro}
      showBackButton={showBackButton}
      onBackButtonClick={onBackButtonClick}
      topSection={topSection}
      showProgress={showProgress}
      showSideMenu={showSideMenu}
      layoutType={layoutType}
      taskProgressComponent={taskProgressComponent}
      pagePathName={pagePathName}
      customMenuItems={menuItems}
      renderSideMenu={(sideMenuProps) => (
        <SideMenu
          menuItems={sideMenuProps.menuItems}
          showBackButton={sideMenuProps.showBackButton}
          showProgress={sideMenuProps.showProgress}
          taskProgressComponent={sideMenuProps.taskProgressComponent}
          onBackButtonClick={sideMenuProps.onBackButtonClick}
        >
          {sideMenuProps.intro}
        </SideMenu>
      )}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default AssetDataLayout;
