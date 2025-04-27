'use client';

import React, { useMemo, useEffect, useCallback, useState } from 'react';
import Link from 'next/link';
import Icon from '@/components/icon';
import sideMenuStyle from './index.module.scss';
import useApiClient from '@/utils/request';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { MenuItem } from '@/types/index';
import { useRelationships } from '@/app/cmdb/context/relationships';

interface SideMenuProps {
  menuItems: MenuItem[];
  children?: React.ReactNode;
  showBackButton?: boolean;
  showProgress?: boolean;
  taskProgressComponent?: React.ReactNode;
  onBackButtonClick?: () => void;
}

interface ListItem {
  text: string;
  value?: number;
  model_asst_id: string;
}
interface ModelAssociation {
  _id: number;
  _label: string;
  is_pre: boolean;
  mapping: string;
  model_asst_id: string;
  asst_id: string;
  src_id: number;
  src_model_id: string;
  dst_id: number;
  dst_model_id: string;
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
  const { get } = useApiClient();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const modelId = searchParams.get('model_id');
  const { setSelectedAssoId, assoInstances, assoTypes, modelList } =
    useRelationships();
  const [allAssociations, setAllAssociations] = useState<ModelAssociation[]>(
    []
  );

  const handleItemClick = (modelAsstId: string, item: MenuItem) => {
    if (!isActive(item.url)) {
      const newUrl = buildUrlWithParams(item.url);
      router.push(newUrl);
    }
    setSelectedAssoId(modelAsstId);
  };

  const buildUrlWithParams = (path: string) => {
    const params = new URLSearchParams(searchParams);
    return `${path}?${params.toString()}`;
  };

  const isActive = (path: string): boolean => {
    if (pathname === null) return false;
    return pathname.startsWith(path);
  };

  useEffect(() => {
    fetchAllAssociations(modelId || '');
  }, []);

  const fetchAllAssociations = useCallback(async (modelId: string) => {
    if (!modelId) return;
    try {
      const data = await get(`/cmdb/api/model/${modelId}/association`);
      setAllAssociations(Array.isArray(data) ? data : []);
    } catch {
      setAllAssociations([]);
    }
  }, []);

  const relationData = useMemo(() => {
    if (!assoInstances?.length) return [];

    const filterAssoList: any = allAssociations.filter((item) => {
      return assoInstances.every(
        (asso) => asso.model_asst_id !== item.model_asst_id
      );
    });
    const groupedData = assoInstances
      .concat(filterAssoList)
      .reduce((acc, item) => {
        const title =
          assoTypes.find((type) => type.asst_id === item.asst_id)?.asst_name ||
          '--';
        if (!acc.has(title)) {
          acc.set(title, []);
        }

        const text =
          modelList.find(
            (model) =>
              model.model_id ===
              (item.dst_model_id === modelId
                ? item.src_model_id
                : item.dst_model_id)
          )?.model_name || '--';

        acc.get(title)?.push({
          model_asst_id: item.model_asst_id,
          text,
          value: item.inst_list?.length || 0,
        });

        return acc;
      }, new Map());

    return Array.from(groupedData.entries()).map(([title, children]) => ({
      title,
      children,
    }));
  }, [assoInstances, assoTypes, allAssociations, modelList]);

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
      <nav className={`flex-1 relative rounded-md ${sideMenuStyle.nav}`}>
        <ul className="p-3 h-full">
          {menuItems.map((item) => (
            <React.Fragment key={item.url}>
              <li
                className={`rounded-md mb-1 ${isActive(item.url) ? sideMenuStyle.active : ''}`}
              >
                <Link legacyBehavior href={buildUrlWithParams(item.url)}>
                  <a
                    className={`group flex items-center h-9 rounded-md py-2 text-sm font-normal px-3`}
                  >
                    {item.icon && (
                      <Icon type={item.icon} className="text-xl pr-1.5" />
                    )}
                    {item.title}
                  </a>
                </Link>
              </li>
              {item.name === ASSET_NAME && !!relationData?.length && (
                <div
                  className={`ml-4 mt-2 mb-2 pb-1 border-b border-gray-200 ${sideMenuStyle.relationList}`}
                >
                  {relationData.map((section, index) => (
                    <div key={section.title + index} className="mb-2">
                      <div className="text-gray-400 text-xs mb-2">
                        {section.title}
                      </div>
                      <div className="ml-3">
                        {section.children.map(
                          (subItem: ListItem, itemIndex: number) => (
                            <div
                              key={itemIndex}
                              className="flex justify-between items-center p-1 cursor-pointer hover:bg-gray-100 rounded-md"
                              onClick={() =>
                                handleItemClick(subItem.model_asst_id, item)
                              }
                            >
                              <EllipsisWithTooltip
                                text={subItem.text}
                                className="w-[100px] overflow-hidden text-ellipsis whitespace-nowrap"
                              />
                              <span className="bg-gray-100 px-2 py-0.5 rounded text-xs text-gray-600">
                                {subItem.value}
                              </span>
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
