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
import { useClassificationApi, useInstanceApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';

const DEFAULT_MODEL_ICON_URL =
  '/assets/icons-realistic/cc-default_默认.svg';

const handleModelIconError = (
  event: React.SyntheticEvent<HTMLImageElement>
) => {
  const image = event.currentTarget;
  if (image.dataset.fallbackApplied === 'true') {
    image.style.visibility = 'hidden';
    return;
  }

  image.dataset.fallbackApplied = 'true';
  image.src = DEFAULT_MODEL_ICON_URL;
};

const AssetsOverview: React.FC = () => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const router = useRouter();
  const commonContext = useCommon();
  const modelListFromContext = commonContext?.modelList || [];
  const [loading, setLoading] = useState<boolean>(false);
  const [overViewList, setOverViewList] = useState<GroupItem[]>([]);
  const [allOverViewList, setAllOverViewList] = useState<GroupItem[]>([]);

  const { getClassificationList } = useClassificationApi();
  const { getModelInstanceCount } = useInstanceApi();

  useEffect(() => {
    if (isLoading || modelListFromContext.length === 0) return;
    fetchAssetsOverviewList();
  }, [isLoading, modelListFromContext]);

  const breakpointColumnsObj = {
    default: 6,
    1600: 5,
    1300: 4,
    1000: 3,
    700: 2,
    500: 1,
  };

  const handleSearch = (value: string) => {
    const keyword = value.trim().toLowerCase();
    if (!keyword) {
      setOverViewList(allOverViewList);
      return;
    }

    const list = allOverViewList.filter((item) =>
      item.list.find((tex) =>
        tex.model_name.toLowerCase().includes(keyword)
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

  const fetchAssetsOverviewList = async () => {
    setLoading(true);
    try {
      const [groupData, instCount] = await Promise.all([
        getClassificationList(),
        getModelInstanceCount(),
      ]);

      const groups = deepClone(groupData).map((item: GroupItem) => ({
        ...item,
        list: [],
      }));

      modelListFromContext.forEach((modelItem: ModelItem) => {
        const target = groups.find(
          (item: GroupItem) =>
            item.classification_id === modelItem.classification_id
        );
        if (target) {
          modelItem.count = instCount[modelItem.model_id] || 0;
          target.list.push(modelItem);
        }
      });

      setOverViewList(groups);
      setAllOverViewList(groups);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={assetsOverviewStyle.assetsOverview}>
      <Spin spinning={loading}>
        <Input.Search
          className={assetsOverviewStyle.searchInput}
          allowClear
          size="large"
          placeholder={t('common.search')}
          aria-label={t('common.search')}
          onSearch={handleSearch}
          onClear={() => setOverViewList(allOverViewList)}
        />
        {overViewList.length ? (
          <Masonry
            breakpointCols={breakpointColumnsObj}
            className={assetsOverviewStyle['my-masonry-grid']}
            columnClassName="my-masonry-grid_column"
          >
            {overViewList.map((item) => (
              <section
                key={item.classification_id}
                className={assetsOverviewStyle.card}
              >
                <EllipsisWithTooltip
                  text={item.classification_name}
                  className={assetsOverviewStyle.title}
                />
                <ul className={assetsOverviewStyle.list}>
                  {item.list.map((sec) => (
                    <li key={sec.model_id}>
                      <div
                        className={assetsOverviewStyle.listItem}
                        onClick={() => linkToDetial(sec)}
                      >
                        <div className={assetsOverviewStyle.leftSide}>
                          <span
                            className={assetsOverviewStyle.modelIcon}
                            aria-hidden="true"
                          >
                            <Image
                              src={getIconUrl(sec)}
                              alt=""
                              width={18}
                              height={18}
                              onError={handleModelIconError}
                            />
                          </span>
                          <EllipsisWithTooltip
                            text={sec.model_name}
                            className={assetsOverviewStyle.modelName}
                          />
                        </div>
                        <span className={assetsOverviewStyle.countGroup}>
                          <span
                            className={`${assetsOverviewStyle.rightSide} ${
                              Number(sec.count) > 0
                                ? assetsOverviewStyle.activeCount
                                : ''
                            }`}
                          >
                            {sec.count}
                          </span>
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
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
