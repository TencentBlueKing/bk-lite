import React, { useState, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { Popover, Spin, Tour } from 'antd';
import { CaretDownFilled } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { usePermissions } from '@/context/permissions';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import styles from './index.module.scss';
import type { TourProps } from 'antd';
import { TourItem } from '@/types/index';
import UserInfo from '../user-info';
import Icon from '@/components/icon';

const TOUR_VIEWED_KEY_PREFIX = 'tour_viewed';

const TopMenu = () => {
  const { t } = useTranslation();
  const { menus: menuItems } = usePermissions();
  const pathname = usePathname();
  const { clientData, loading } = useClientData();
  const { userId } = useUserInfoContext();
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState<TourProps['steps']>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [hasViewedTour, setHasViewedTour] = useState(false);

  const menuRefs = useRef<{ [key: string]: React.RefObject<HTMLAnchorElement> }>({});

  const getTourViewedKey = () => {
    return `${userId}_${TOUR_VIEWED_KEY_PREFIX}`;
  };

  useEffect(() => {
    menuItems.forEach((item) => {
      if (item.tour && !menuRefs.current[item.url]) {
        menuRefs.current[item.url] = React.createRef();
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
      .filter(item => item.tour)
      .map(item => ({
        menuItem: item,
        tour: item.tour as TourItem
      }))
      .sort((a, b) => a.tour.order - b.tour.order);

    if (tours.length > 0) {
      const steps = tours.map(({ menuItem, tour }) => {
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

  const handleTourChange: TourProps['onChange'] = (current) => {
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
    window.open('https://wd.canway.net/?cat=27', '_blank');
  };

  const isConsole = process.env.NEXT_PUBLIC_IS_OPS_CONSOLE === 'true';

  const renderContent = loading ? (
    <div className="flex justify-center items-center h-32">
      <Spin tip="Loading..." />
    </div>
  ) : (
    <div className="grid grid-cols-3 gap-4 max-h-[350px] overflow-auto">
      {clientData.map((app) => (
        <div
          key={app.name}
          className={`group flex flex-col items-center p-4 rounded-sm cursor-pointer ${styles.navApp}`}
          onClick={() => window.open(app.url, '_blank')}
        >
          <Icon
            type={app.client_id || 'yingyongxitongguanli'}
            className="text-2xl mb-1 transition-transform duration-300 transform group-hover:scale-125"
          />
          {app.name}
        </div>
      ))}
    </div>
  );

  return (
    <div className="z-30 flex flex-col grow-0 shrink-0 w-full basis-auto h-[56px] relative">
      <div className="flex items-center justify-between px-4 w-full h-full">
        <div className="flex items-center space-x-2">
          <Image src="/logo-site.png" className="block w-auto h-10" alt="logo" width={100} height={40} />
          <div className="font-medium">WeOps X</div>
          {!isConsole && (
            <Popover content={renderContent} title={t('common.appList')} trigger="hover">
              <div className={`flex items-center justify-center cursor-pointer rounded-[10px] px-3 py-2 ${styles.nav}`}>
                <Icon type="caidandaohang" className="mr-1" />
                <CaretDownFilled className={`text-sm ${styles.icons}`} />
              </div>
            </Popover>
          )}
        </div>
        <div className="flex items-center flex-shrink-0 space-x-2">
          {hasViewedTour && (
            <div
              className="text-xs flex items-center mr-2 text-[var(--color-text-3)] cursor-pointer hover:text-[var(--color-primary)]"
              onClick={handleDocumentClick}
            >
              <Icon type="shiyongwendang" className="mr-1" />
              {t('common.officialDocument')}
            </div>
          )}
          <UserInfo />
        </div>
      </div>
      <div className="absolute left-1/2 top-1/2 transform -translate-x-1/2 -translate-y-1/2">
        <div className="flex items-center space-x-4">
          {menuItems
            .filter((item) => item.url && !item.isNotMenuItem)
            .map((item) => {
              const isActive = item.url === '/' ? pathname === '/' : pathname?.startsWith(item.url);
              return (
                <Link key={item.url} href={item.url} prefetch={false} legacyBehavior>
                  <a
                    ref={menuRefs.current[item.url] || null}
                    id={item.name}
                    className={`px-3 py-2 rounded-[10px] flex items-center ${styles.menuCol} ${isActive ? styles.active : ''}`}
                  >
                    <Icon type={item.icon} className="mr-2 w-4 h-4" />
                    {item.title}
                  </a>
                </Link>
              );
            })}
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
