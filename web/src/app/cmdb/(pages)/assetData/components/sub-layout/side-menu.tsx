'use client';

import React, { useMemo, useEffect, useState } from 'react';
import Link from 'next/link';
import Icon from '@/components/icon';
import sideMenuStyle from './index.module.scss';
import { useInstanceApi } from '@/app/cmdb/api';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import {
  ArrowLeftOutlined, ApartmentOutlined, AppstoreOutlined, HddOutlined,
} from '@ant-design/icons';
import { MenuItem } from '@/types/index';
import { useTranslation } from '@/utils/i18n';
import {
  buildRelationshipTabHref,
  DEFAULT_RELATIONSHIP_TAB,
  isRelationshipMenuActive,
} from '../../relationshipViewNavigation';

interface SideMenuProps {
  menuItems: MenuItem[];
  children?: React.ReactNode;
  showBackButton?: boolean;
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  onBackButtonClick?: () => void;
}

const SideMenu: React.FC<SideMenuProps> = ({
  menuItems,
  children,
  showBackButton = true,
  showProgress = false,
  taskProgressComponent,
  onBackButtonClick,
}) => {
  const ASSET_NAME = 'asset_relationships';
  const IP_VIEW_NAME = 'asset_ip_view';

  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const modelId = searchParams.get('model_id');

  // 左侧快捷入口：网络拓扑 / 应用拓扑 / 机房视图 / 机柜视图，直达关联关系页对应子视图（缩短操作路径）
  const { getTopoThemes } = useInstanceApi();
  const { t } = useTranslation();
  const [themes, setThemes] = useState<string[]>([]);
  const currentTab = searchParams.get('tab') || '';

  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    getTopoThemes(modelId)
      .then((res: { themes: string[] }) => {
        if (!cancelled) setThemes(res?.themes || []);
      })
      .catch(() => {
        if (!cancelled) setThemes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  const relItem = menuItems.find((m) => m.name === ASSET_NAME);
  const shortcuts = useMemo(() => {
    const list: { tab: string; title: string; icon: React.ReactNode }[] = [];
    if (themes.includes('network')) {
      list.push({ tab: 'network', title: t('Model.networkTopo'), icon: <ApartmentOutlined /> });
    }
    if (themes.includes('app_overview')) {
      list.push({ tab: 'appOverview', title: t('Model.applicationResourceOverview'), icon: <ApartmentOutlined /> });
    }
    if (modelId === 'server_room') {
      list.push({ tab: 'roomView', title: t('Model.roomLayout'), icon: <AppstoreOutlined /> });
    }
    if (modelId === 'rack') {
      list.push({ tab: 'rackView', title: t('Model.rackElevation'), icon: <HddOutlined /> });
    }
    return list;
  }, [themes, modelId, t]);

  const goShortcut = (tab: string) => {
    if (!relItem?.url) return;
    const params = new URLSearchParams(searchParams);
    params.set('tab', tab);
    router.push(`${relItem.url}?${params.toString()}`);
  };

  const buildUrlWithParams = (path: string) => {
    const params = new URLSearchParams(searchParams);
    return `${path}?${params.toString()}`;
  };

  const shortcutTabs = shortcuts.map((shortcut) => shortcut.tab);

  const isActive = (path: string): boolean => {
    if (pathname === null) return false;
    return pathname.startsWith(path);
  };

  const isMenuItemActive = (item: MenuItem): boolean => {
    const pathMatches = isActive(item.url);
    if (item.name !== ASSET_NAME) return pathMatches;
    return isRelationshipMenuActive(pathMatches, currentTab, shortcutTabs);
  };

  const orderedMenuItems = useMemo(() => {
    const items = [...menuItems];
    const ipViewIndex = items.findIndex((item) => item.name === IP_VIEW_NAME);
    const relationIndex = items.findIndex((item) => item.name === ASSET_NAME);
    if (ipViewIndex === -1 || relationIndex === -1 || ipViewIndex < relationIndex) {
      return items;
    }
    const [ipViewItem] = items.splice(ipViewIndex, 1);
    items.splice(relationIndex, 0, ipViewItem);
    return items;
  }, [menuItems]);

  return (
    <aside
      className={`w-[216px] pr-4 flex flex-shrink-0 flex-col h-full ${sideMenuStyle.sideMenu}`}
    >
      {children && (
        <div
          className={`p-4 rounded-md mb-3 h-[80px] ${sideMenuStyle.introduction}`}
        >
          {children}
        </div>
      )}
      <nav
        className={`flex flex-1 overflow-hidden relative rounded-md ${sideMenuStyle.nav}`}
      >
        <ul className="p-3 flex-1">
          {orderedMenuItems.map((item) => (
            <React.Fragment key={item.url}>
              {item.name === ASSET_NAME && shortcuts.map((s) => {
                const active = isActive(item.url) && currentTab === s.tab;
                return (
                  <li
                    key={`sc-${s.tab}`}
                    className={`rounded-md mb-1 ${active ? sideMenuStyle.active : ''}`}
                  >
                    <a
                      className="group flex items-center h-9 rounded-md py-2 text-sm font-normal px-3 cursor-pointer"
                      onClick={() => goShortcut(s.tab)}
                    >
                      <span className="text-base pr-1.5 inline-flex items-center">
                        {s.icon}
                      </span>
                      {s.title}
                    </a>
                  </li>
                );
              })}
              <li
                className={`rounded-md mb-1 ${isMenuItemActive(item) ? sideMenuStyle.active : ''}`}
              >
                <Link
                  href={item.name === ASSET_NAME
                    ? buildRelationshipTabHref(
                      item.url,
                      searchParams,
                      DEFAULT_RELATIONSHIP_TAB
                    )
                    : buildUrlWithParams(item.url)}
                  className="group flex items-center h-9 rounded-md py-2 text-sm font-normal px-3"
                >
                  {item.icon && (
                    <Icon type={item.icon} className="text-xl pr-1.5" />
                  )}
                  {item.title}
                </Link>
              </li>
            </React.Fragment>
          ))}
        </ul>
        {showProgress && <>{taskProgressComponent}</>}
        {showBackButton && (
          <button
            className="absolute bottom-4 left-4 flex items-center py-2 rounded-md text-sm"
            onClick={onBackButtonClick}
          >
            <ArrowLeftOutlined className="mr-2" />
          </button>
        )}
      </nav>
    </aside>
  );
};

export default SideMenu;
