'use client';

import React from 'react';
import Link from 'next/link';
import Icon from '@/components/icon';
import { MenuItem } from '@/types/index';

interface SideMenuNavListProps {
  menuItems: MenuItem[];
  buildHref: (item: MenuItem) => string;
  isItemActive: (item: MenuItem) => boolean;
  onItemClick?: (item: MenuItem) => void;
  renderBeforeItem?: (item: MenuItem) => React.ReactNode;
  renderAfterItem?: (item: MenuItem) => React.ReactNode;
  listClassName?: string;
  itemClassName?: string;
  activeItemClassName?: string;
  linkClassName?: string;
}

const SideMenuNavList: React.FC<SideMenuNavListProps> = ({
  menuItems,
  buildHref,
  isItemActive,
  onItemClick,
  renderBeforeItem,
  renderAfterItem,
  listClassName = 'p-3',
  itemClassName = 'rounded-md mb-1',
  activeItemClassName = '',
  linkClassName = 'group flex items-center h-9 rounded-md py-2 text-sm font-normal px-3',
}) => {
  return (
    <ul className={listClassName}>
      {menuItems.map((item) => {
        const active = isItemActive(item);
        const href = buildHref(item);

        return (
          <React.Fragment key={item.url || item.name}>
            {renderBeforeItem?.(item)}
            <li className={`${itemClassName} ${active ? activeItemClassName : ''}`.trim()}>
              <Link legacyBehavior href={href}>
                <a className={linkClassName} onClick={() => onItemClick?.(item)}>
                  {item.icon && <Icon type={item.icon} className="text-xl pr-1.5" />}
                  {item.title}
                </a>
              </Link>
            </li>
            {renderAfterItem?.(item)}
          </React.Fragment>
        );
      })}
    </ul>
  );
};

export default SideMenuNavList;
