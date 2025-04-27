'use client';
import React, { useEffect, useState } from 'react';
import Masonry from 'react-masonry-css';
import assetsOverviewStyle from './index.module.scss';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { GroupItem, ModelItem } from '@/app/cmdb/types/assetManage';
import { deepClone, getIconUrl } from '@/app/cmdb/utils/common';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { Spin, Input, Empty } from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

const AssetsOverview: React.FC = () => {
  const { get, isLoading } = useApiClient();
  const { t } = useTranslation();
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(false);
  const [overViewList, setOverViewList] = useState<GroupItem[]>([]);
  const [allOverViewList, setAllOverViewList] = useState<GroupItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');

  useEffect(() => {
    if (isLoading) return;
    fetchAssetsOverviewList();
  }, [get, isLoading]);

  const breakpointColumnsObj = {
    default: 6,
    1600: 5,
    1300: 4,
    1000: 3,
    700: 2,
    500: 1,
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const handleSearch = () => {
    const list = allOverViewList.filter((item) =>
      item.list.find((tex) =>
        tex.model_name.toLowerCase().includes(searchText.toLowerCase())
      )
    );
    setOverViewList(list);
  };

  const linkToDetial = (item: ModelItem) => {
    const params = new URLSearchParams({
      modelId: item.model_id,
      classificationId: item.classification_id,
    }).toString();
    router.push(`/cmdb/assetData?${params}`);
  };

  const handleClear = () => {
    setSearchText('');
    setOverViewList(allOverViewList);
  };

  const fetchAssetsOverviewList = () => {
    const getCroupList = get('/cmdb/api/classification/');
    const getModelList = get('/cmdb/api/model/');
    const getModelInstCount = get('/cmdb/api/instance/model_inst_count/');
    setLoading(true);
    try {
      Promise.all([getModelList, getCroupList, getModelInstCount])
        .then((res) => {
          const modeldata: ModelItem[] = res[0];
          const groupData: GroupItem[] = res[1];
          const groups = deepClone(groupData).map((item: GroupItem) => ({
            ...item,
            list: [],
          }));
          modeldata.forEach((modelItem: ModelItem) => {
            const target = groups.find(
              (item: GroupItem) =>
                item.classification_id === modelItem.classification_id
            );
            if (target) {
              modelItem.count = res[2][modelItem.model_id] || 0;
              target.list.push(modelItem);
            }
          });
          setOverViewList(groups);
          setAllOverViewList(groups);
        })
        .finally(() => {
          setLoading(false);
        });
    } catch (error) {
      console.error(error);
      setLoading(false);
    }
  };

  return (
    <div className={assetsOverviewStyle.assetsOverview}>
      <Spin spinning={loading}>
        <Input
          className="w-[320px]"
          value={searchText}
          allowClear
          placeholder={t('search')}
          onPressEnter={handleSearch}
          onClear={handleClear}
          onChange={handleTextChange}
        />
        {overViewList.length ? (
          <Masonry
            breakpointCols={breakpointColumnsObj}
            className={assetsOverviewStyle['my-masonry-grid']}
            columnClassName="my-masonry-grid_column"
          >
            {overViewList.map((item) => (
              <div
                key={item.classification_id}
                className={`bg-[var(--color-bg-1)] p-[10px] mb-[20px] rounded`}
              >
                <h2
                  className={`${assetsOverviewStyle.title} text-[16px] font-[600]`}
                >
                  {item.classification_name}
                </h2>
                <ul className={assetsOverviewStyle.list}>
                  {item.list.map((sec) => (
                    <li
                      className={assetsOverviewStyle.listItem}
                      key={sec.model_id}
                      onClick={() => linkToDetial(sec)}
                    >
                      <span className={assetsOverviewStyle.leftSide}>
                        <Image
                          src={getIconUrl(sec)}
                          className="block w-auto h-10"
                          alt={t('picture')}
                          width={20}
                          height={20}
                        />
                        <EllipsisWithTooltip
                          text={sec.model_name}
                          className="overflow-hidden text-ellipsis whitespace-nowrap"
                        />
                      </span>
                      <span className={assetsOverviewStyle.rightSide}>
                        {sec.count}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </Masonry>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Spin>
    </div>
  );
};

export default AssetsOverview;
