'use client';

import React, { useState } from 'react';
import { Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams, useRouter } from 'next/navigation';
import { OBJECT_ICON_MAP } from '@/app/monitor/constants/monitor';
import Icon from '@/components/icon';
import detailStyle from '../index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import Overview from './overview';
import Metric from './metric';

const ViewDetail = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const desc = searchParams.get('instance_name');
  const icon = OBJECT_ICON_MAP[searchParams.get('name') || ''];
  const monitorObjDisplayName: string =
    searchParams.get('monitorObjDisplayName') || '';
  const monitorObjectId: React.Key = searchParams.get('monitorObjId') || '';
  const monitorObjectName: string = searchParams.get('name') || '';
  const instanceId: React.Key = searchParams.get('instance_id') || '';
  const instanceName: string = searchParams.get('instance_name') || '';
  const idValues: string[] = (
    searchParams.get('instance_id_values') || ''
  ).split(',');
  const [activeMenu, setActiveMenu] = useState<string>('metrics');

  const onTabChange = (val: string) => {
    setActiveMenu(val);
  };

  const onBackButtonClick = () => {
    const targetUrl = `/monitor/view`;
    router.push(targetUrl);
  };

  return (
    <div className={detailStyle.detail}>
      <div className={detailStyle.leftSide}>
        <div className={detailStyle.topIntro}>
          <Icon
            type={icon || 'Host'}
            className="mr-[10px] text-[30px] min-w-[30px]"
          />
          <span className="flex items-center">
            <span
              className="w-[140px] hide-text"
              title={`${monitorObjDisplayName} - ${desc}`}
            >
              {monitorObjDisplayName} -
              <span className="text-[12px] text-[var(--color-text-3)] ml-[4px]">
                {desc}
              </span>
            </span>
          </span>
        </div>
        <div className={detailStyle.menu}>
          <Segmented
            vertical
            value={activeMenu}
            className="custom-tabs"
            options={[
              { value: 'metrics', label: t('monitor.views.metrics') },
              //   { value: 'overview', label: t('monitor.views.overview') },
            ]}
            onChange={onTabChange}
          />
          <button
            className="absolute bottom-4 left-4 flex items-center py-2 rounded-md text-sm"
            onClick={onBackButtonClick}
          >
            <ArrowLeftOutlined className="mr-2" />
          </button>
        </div>
      </div>
      <div className={detailStyle.rightSide}>
        {activeMenu === 'metrics' ? (
          <Metric
            idValues={idValues}
            monitorObjectId={monitorObjectId}
            monitorObjectName={monitorObjectName}
            instanceId={instanceId}
            instanceName={instanceName}
          />
        ) : (
          <Overview
            idValues={idValues}
            monitorObjectId={monitorObjectId}
            monitorObjectName={monitorObjectName}
            instanceId={instanceId}
            instanceName={instanceName}
          />
        )}
      </div>
    </div>
  );
};

export default ViewDetail;
