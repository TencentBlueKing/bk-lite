import React from 'react';
import Icon from '@/components/icon';
import menu from '@/app/alarm/constants/menu.json';
import commonStyles from './index.module.scss';
import { usePathname } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { Breadcrumb } from 'antd';
interface Props {
  children?: React.ReactNode;
}

interface Crumb {
  title: string;
  url: string;
}

const PageBreadcrumb: React.FC<Props> = ({ children }) => {
  const router = useScreenAwareRouter();
  const pathname = usePathname();
  const parentPath =
    pathname.lastIndexOf('/') > 0
      ? pathname.substring(0, pathname.lastIndexOf('/'))
      : '/';
  const locale = localStorage.getItem('locale') || 'en';
  const zhMenus = menu[locale === 'en' ? 'en' : 'zh'] || [];
  const crumbs: Crumb[] = [];

  for (const item of zhMenus) {
    if (item.url === pathname) {
      crumbs.push({ title: item.title, url: item.url });
      break;
    }
    if (item.children) {
      const child = item.children.find((c) => c.url === pathname);
      if (child) {
        crumbs.push(
          { title: item.title, url: item.url },
          { title: child.title, url: child.url }
        );
        break;
      }
    }
  }

  return (
    <Breadcrumb className={commonStyles.breadcrumb}>
      <Breadcrumb.Item
        onClick={() => router.push(parentPath)}
        className={commonStyles.backIcon}
      >
        <Icon type="xiangzuojiantou" />
      </Breadcrumb.Item>
      {crumbs.map(({ title, url }, idx) => {
        const isCurrent = url === pathname;
        return (
          <Breadcrumb.Item
            key={idx}
            onClick={() => !isCurrent && router.push(url)}
            className={!isCurrent ? commonStyles.link : undefined}
          >
            {title}
          </Breadcrumb.Item>
        );
      })}
      {children}
    </Breadcrumb>
  );
};

export default PageBreadcrumb;
