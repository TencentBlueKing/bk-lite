import React, { useState, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Popover, Spin, Tour, Tooltip } from 'antd';
import { CaretDownFilled } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { usePermissions } from '@/context/permissions';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import { usePortalBranding } from '@/hooks/usePortalBranding';
import { findMatchedMenuPath, resolveMenuIcon } from '@/utils/menuHelpers';
import { APP_TOP_SIDE_RAIL_WIDTH_PX, useConsoleLayout } from '@/console-layout';
import styles from './index.module.scss';
import type { TourProps } from 'antd';
import { TourItem, MenuItem, ClientData } from '@/types/index';
import UserInfo from './user-info';
import Notifications from '@/components/notifications';
import Icon from '@/components/icon';
import AppTopNav from './appTopNav';
import { resolveAppDisplayName } from '@/utils/appDisplayName';

const TOUR_VIEWED_KEY_PREFIX = 'tour_viewed';

interface TopMenuProps {
  hideMainMenu?: boolean;
  hideBrand?: boolean;
}

const TopMenu: React.FC<TopMenuProps> = ({ hideMainMenu, hideBrand }) => {
  const { t } = useTranslation();
  const { menus: menuItems } = usePermissions();
  const pathname = usePathname();
  const { clientData, appConfigList, loading, appConfigLoading } = useClientData();
  const { userId } = useUserInfoContext();
  const { portalName, logoUrl } = usePortalBranding();
  const { layout: chromeLayout } = useConsoleLayout();
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState<TourProps['steps']>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [hasViewedTour, setHasViewedTour] = useState(false);

  const menuRefs = useRef<{ [key: string]: React.RefObject<HTMLAnchorElement> }>({});

  const getTourViewedKey = () => {
    return `${userId}_${TOUR_VIEWED_KEY_PREFIX}`;
  };

  useEffect(() => {
    menuItems.forEach((item: MenuItem) => {
      if (item.tour && !menuRefs.current[item.url]) {
        menuRefs.current[item.url] = React.createRef() as any;
      }
    });

    if (userId) {
      try {
        const tourViewedKey = getTourViewedKey();
        const viewed = localStorage.getItem(tourViewedKey) === 'true';
        setHasViewedTour(viewed);

        if (!viewed) {
          prepareTourSteps();
        }
      } catch (error) {
        console.warn('Unable to access localStorage:', error);
      }
    }
  }, [menuItems, userId]);

  const prepareTourSteps = () => {
    const tours = menuItems
      .filter((item: MenuItem) => item.tour)
      .map((item: MenuItem) => ({
        menuItem: item,
        tour: item.tour as TourItem
      }))
      .sort((a: { menuItem: MenuItem; tour: TourItem }, b: { menuItem: MenuItem; tour: TourItem }) => a.tour.order - b.tour.order);

    if (tours.length > 0) {
      const steps = tours.map(({ menuItem, tour }: { menuItem: MenuItem; tour: TourItem }) => {
        const step: NonNullable<TourProps['steps']>[0] = {
          title: tour.title,
          description: tour.description,
          target: () => {
            if (tour.target === menuItem.name) {
              const element = menuRefs.current[menuItem.url]?.current;
              return element || document.body;
            }
            const element = document.getElementById(tour.target);
            return element || document.body;
          },
        };

        if (tour.cover) {
          step.cover = (
            <img
              alt={tour.title}
              src={tour.cover}
            />
          );
        }

        if (tour.mask) {
          step.mask = tour.mask;
        }

        return step;
      });

      setTourStep(steps);

      // Show tour automatically if user hasn't viewed it before
      if (!hasViewedTour && steps.length > 0) {
        setTourOpen(true);
      }
    }
  };

  const handleTourChange: TourProps['onChange'] = (current: number) => {
    setCurrentStep(current);
  };

  const handleCloseTour = () => {
    setTourOpen(false);

    if (userId) {
      try {
        const tourViewedKey = getTourViewedKey();
        localStorage.setItem(tourViewedKey, 'true');
        setHasViewedTour(true);
      } catch (error) {
        console.warn('Unable to save tour viewed state to localStorage:', error);
      }
    }
  };

  const handleDocumentClick = () => {
    window.open('https://github.com/TencentBlueKing/bk-lite', '_blank');
  };

  const apps = appConfigList.length > 0 ? appConfigList : clientData;
  const showBrand = !hideBrand;
  const showAppSwitcher = chromeLayout === 'classic';
  const showAppTopNav = chromeLayout === 'app-top';
  const appTopBrandGrid = showAppTopNav && showBrand;

  const renderContent = (loading || appConfigLoading) ? (
    <div className="flex justify-center items-center h-32">
      <Spin />
    </div>
  ) : (
    <div className="grid grid-cols-4 gap-4 max-h-[420px] overflow-auto">
      {(apps).map((app: ClientData) => (
        <div
          key={app.name}
          className={`group flex flex-col items-center p-4 rounded-sm cursor-pointer ${styles.navApp}`}
          onClick={() => window.open(app.url, '_blank')}
        >
          <Icon
            type={app.icon || app.name}
            className="text-2xl mb-1 transition-transform duration-300 transform group-hover:scale-125"
          />
          {resolveAppDisplayName(app, t)}
        </div>
      ))}
    </div>
  );

  return (
    <div className="relative z-30 h-[56px] w-full shrink-0 grow-0">
      <div
        className={`grid h-full w-full items-center ${
          appTopBrandGrid
            ? ''
            : showAppTopNav
              ? 'grid-cols-[minmax(0,1fr)_auto] px-4'
              : 'grid-cols-[1fr_auto_1fr] px-4'
        }`}
        style={
          appTopBrandGrid
            ? { gridTemplateColumns: `${APP_TOP_SIDE_RAIL_WIDTH_PX}px minmax(0,1fr) auto` }
            : undefined
        }
      >
        {showBrand && (
        <div
          data-testid={showAppTopNav ? 'app-top-brand' : undefined}
          className={
            showAppTopNav
              ? 'z-10 flex h-full items-center space-x-2 px-4'
              : 'z-10 flex items-center justify-self-start space-x-2'
          }
          style={showAppTopNav ? { width: APP_TOP_SIDE_RAIL_WIDTH_PX } : undefined}
        >
          <img src={logoUrl} className="block h-10 w-auto object-contain" alt="logo" />
          <div className="font-medium">{portalName}</div>
          {showAppSwitcher && (
            <Popover content={renderContent} title={t('common.appList')} trigger="hover">
              <div className={`flex cursor-pointer items-center justify-center rounded-[10px] px-3 py-2 ${styles.nav}`}>
                <Icon type="caidandaohang" className="mr-1" />
                <CaretDownFilled className={`text-sm ${styles.icons}`} />
              </div>
            </Popover>
          )}
        </div>
        )}
        <div className={showAppTopNav ? `z-10 min-w-0 w-full ${appTopBrandGrid ? 'pl-4' : ''}` : 'z-10'}>
          {showAppTopNav ? (
            <AppTopNav apps={apps} pathname={pathname} />
          ) : !hideMainMenu ? (
          <div
            className="z-10 flex items-center justify-self-center space-x-4 overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
            style={{ whiteSpace: 'nowrap' }}
          >
            {menuItems
              .filter((item: MenuItem) => item.url && !item.isNotMenuItem)
              .map((item: MenuItem) => {
                // Find the matched menu path to determine active state
                const matchedPath = pathname ? findMatchedMenuPath(menuItems, pathname) : null;
                const isActive = matchedPath && matchedPath.length > 0 && matchedPath[0].url === item.url;

                return (
                  <Link
                    key={item.url}
                    href={item.url}
                    prefetch={false}
                    ref={menuRefs.current[item.url] || null}
                    id={item.name}
                    className={`flex items-center rounded-[10px] px-3 py-2 ${styles.menuCol} ${isActive ? styles.active : ''}`}
                  >
                    <Icon type={resolveMenuIcon(item)} className="mr-2 h-4 w-4" />
                    {item.title}
                  </Link>
                );
              })}
            </div>
          ) : (
            <div />
          )}
        </div>
        <div className={`z-10 flex flex-shrink-0 items-center justify-self-end gap-4 ${appTopBrandGrid ? 'pr-4' : ''}`}>
          <Notifications />
          {hasViewedTour && (
            <Tooltip title={t('common.officialDocument')}>
              <div
                className="flex cursor-pointer items-center justify-center text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
                onClick={handleDocumentClick}
              >
                <Icon type="shiyongwendang" className="text-[16px]" />
              </div>
            </Tooltip>
          )}
          <UserInfo />
        </div>
      </div>
      <Tour
        open={tourOpen}
        onClose={handleCloseTour}
        steps={tourStep}
        current={currentStep}
        onChange={handleTourChange}
      />
    </div>
  );
};

export default TopMenu;
