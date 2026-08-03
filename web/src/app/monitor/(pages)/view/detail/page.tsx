'use client';

import React, { useState } from 'react';
import { Breadcrumb, Button, Segmented } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams, useRouter } from 'next/navigation';
import detailStyle from '../index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import Overview from './overview';
import Metric from '@/app/monitor/components/metric-views';
import { getDashboardReturnNavigation } from '@/app/monitor/dashboards/shared/utils';
import { resolveDashboardInstanceIdentity } from '@/app/monitor/dashboards/shared/utils/instance';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

const ViewDetail = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const desc = searchParams.get('instance_name');
  const icon = searchParams.get('icon');
  const monitorObjDisplayName: string =
    searchParams.get('monitorObjDisplayName') || '';
  const monitorObjectId: React.Key = searchParams.get('monitorObjId') || '';
  const monitorObjectName: string = searchParams.get('name') || '';
  const instanceName: string = searchParams.get('instance_name') || '';
  const detailTitle = `${monitorObjDisplayName || monitorObjectName || '监控对象'}指标详情`;
  const returnNavigation = getDashboardReturnNavigation(
    searchParams,
    detailTitle
  );
  // 列表入口已用 JSON 编码 instance_id_values；不可再 split(',')，否则所有进程身份都会被拆坏。
  const { instanceId, idValues } = resolveDashboardInstanceIdentity(searchParams);
  const [activeMenu, setActiveMenu] = useState<string>('metrics');

  const onTabChange = (val: string) => {
    setActiveMenu(val);
  };

  const onBackButtonClick = () => {
    router.push(returnNavigation.href);
  };

  return (
    <div className={detailStyle.detail}>
      <div className={detailStyle.leftSide}>
        <div className={detailStyle.topIntro}>
          <div className="w-[40px] h-[40px] mr-[10px] min-w-[40px] rounded flex items-center justify-center bg-[var(--color-fill-2)]">
            <img
              src={`/assets/icons/${icon || 'cc-default_默认'}.svg`}
              alt={monitorObjDisplayName || monitorObjectName || 'icon'}
              className="w-7 h-7"
              onError={(e) => {
                (e.target as HTMLImageElement).src =
                  '/assets/icons/cc-default_默认.svg';
              }}
            />
          </div>
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
          <div className={detailStyle.menuBody}>
            <Segmented
              vertical
              value={activeMenu}
              className="custom-tabs"
              options={[
                { value: 'metrics', label: t('monitor.views.metrics') }
                //   { value: 'overview', label: t('monitor.views.overview') },
              ]}
              onChange={onTabChange}
            />
          </div>
          <button
            type="button"
            className={detailStyle.backLink}
            onClick={onBackButtonClick}
            title={returnNavigation.label}
          >
            <ArrowLeftOutlined className="mr-2 shrink-0" />
            <EllipsisWithTooltip
              className="min-w-0 truncate"
              text={returnNavigation.label}
            />
          </button>
        </div>
      </div>
      <div className={detailStyle.rightSide}>
        <div className={detailStyle.rightHeader}>
          <Breadcrumb items={returnNavigation.breadcrumbItems} />
          <Button
            className="inline-flex max-w-[260px] items-center"
            icon={<ArrowLeftOutlined />}
            onClick={onBackButtonClick}
          >
            <EllipsisWithTooltip
              className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap"
              text={returnNavigation.label}
            />
          </Button>
        </div>
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
