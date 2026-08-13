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
import { findMatchedMenuPath } from '@/utils/menuHelpers';
import styles from './index.module.scss';
import type { TourProps } from 'antd';
import { TourItem, MenuItem, ClientData } from '@/types/index';
import UserInfo from './user-info';
import Notifications from '@/components/notifications';
import Icon from '@/components/icon';

const TOUR_VIEWED_KEY_PREFIX = 'tour_viewed';

const resolveMenuIcon = (item: MenuItem) => {
  if (item.name === 'wiki_list') return 'zhishiku1';
  return item.icon;
};

interface TopMenuProps {
  hideMainMenu?: boolean;
}

const TopMenu: React.FC<TopMenuProps> = ({ hideMainMenu }) => {
  const { t } = useTranslation();
  const { menus: menuItems } = usePermissions();
  const pathname = usePathname();
  const { clientData, appConfigList, loading, appConfigLoading } = useClientData();
  const { userId } = useUserInfoContext();
  const { portalName, logoUrl } = usePortalBranding();
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

  const renderContent = (loading || appConfigLoading) ? (
    <div className="flex justify-center items-center h-32">
      <Spin />
    </div>
  ) : (
    <div className="grid grid-cols-4 gap-4 max-h-[420px] overflow-auto">
      {(appConfigList.length > 0 ? appConfigList : clientData).map((app: ClientData) => (
        <div
          key={app.name}
          className={`group flex flex-col items-center p-4 rounded-sm cursor-pointer ${styles.navApp}`}
          onClick={() => window.open(app.url, '_blank')}
        >
          <Icon
            type={app.icon || app.name}
            className="text-2xl mb-1 transition-transform duration-300 transform group-hover:scale-125"
          />
          {app.display_name || app.name}
        </div>
      ))}
    </div>
  );

  return (
    <div className="relative z-30 flex h-[104px] w-full grow-0 shrink-0 basis-auto flex-col sm:h-[56px]">
      <div className="flex h-[56px] w-full items-center justify-between px-2 sm:px-4">
        <div className="flex items-center space-x-2">
          <img src={logoUrl} className="block h-8 w-auto object-contain sm:h-10" alt="logo" />
          <div className="hidden font-medium sm:block">{portalName}</div>
          <Popover content={renderContent} title={t('common.appList')} trigger="hover">
            <div className={`flex cursor-pointer items-center justify-center rounded-[10px] px-2 py-2 sm:px-3 ${styles.nav}`}>
              <Icon type="caidandaohang" className="mr-1" />
              <CaretDownFilled className={`text-sm ${styles.icons}`} />
            </div>
          </Popover>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2 sm:gap-4">
          <Notifications />
          {hasViewedTour && (
            <Tooltip title={t('common.officialDocument')}>
              <div
                className="flex items-center justify-center cursor-pointer text-[var(--color-text-3)] hover:text-[var(--color-primary)] transition-colors"
                onClick={handleDocumentClick}
              >
                <Icon type="shiyongwendang" className="text-[16px]" />
              </div>
            </Tooltip>
          )}
          <UserInfo />
        </div>
      </div>
      {!hideMainMenu && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 overflow-x-hidden px-2 sm:bottom-auto sm:top-1/2 sm:-translate-y-1/2">
          <div
            className="pointer-events-auto mx-auto flex w-fit max-w-full items-center space-x-4 overflow-x-auto"
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
                    className={`px-3 py-2 rounded-[10px] flex items-center ${styles.menuCol} ${isActive ? styles.active : ''}`}
                  >
                    <Icon type={resolveMenuIcon(item)} className="mr-2 w-4 h-4" />
                    {item.title}
                  </Link>
                );
              })}
          </div>
        </div>
      )}
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
