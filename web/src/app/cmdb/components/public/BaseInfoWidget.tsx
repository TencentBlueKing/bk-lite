'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { useModelApi, useInstanceApi } from '@/app/cmdb/api';
import { useCmdbUserList } from '@/app/cmdb/context/common';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import InfoList from '@/app/cmdb/(pages)/assetData/detail/baseInfo/list';
import type { AttrFieldType, InstDetail, UserItem } from '@/app/cmdb/types/assetManage';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface BaseInfoWidgetProps {
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
}

const BaseInfoWidget = ({ instUuid, onHeaderAction }: BaseInfoWidgetProps) => {
  const { t } = useTranslation();
  const { getModelAttrGroupsFullInfo } = useModelApi();
  const { getInstanceDetail } = useInstanceApi();
  const apisRef = useRef({ getInstanceDetail, getModelAttrGroupsFullInfo });
  apisRef.current = { getInstanceDetail, getModelAttrGroupsFullInfo };
  const userList: UserItem[] = useCmdbUserList();
  const uuid = resolveCmdbInstUuid(instUuid) || '';
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [instDetail, setInstDetail] = useState<InstDetail>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!uuid) {
      setLoading(false);
      setError(t('common.loadFailed'));
      return;
    }
    setLoading(true);
    setError(null);
    const { getInstanceDetail: fetchDetail, getModelAttrGroupsFullInfo: fetchGroups } =
      apisRef.current;
    fetchDetail(uuid)
      .then(async (detail: InstDetail) => {
        const modelId = String(detail?.model_id || '');
        const groups = modelId
          ? await fetchGroups(modelId)
          : { groups: [] };
        if (cancelled) return;
        setInstDetail(detail);
        setPropertyList(groups.groups || []);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
              'Model.publicWidgetNotFound',
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, uuid]);

  const modelId = String(instDetail.model_id || '');
  const instName = String(instDetail.inst_name || instDetail.name || uuid);
  const hasData = Boolean(propertyList.length || Object.keys(instDetail).length);
  const openHref = hasData && uuid
    ? `/cmdb/assetData/detail/baseInfo?model_id=${encodeURIComponent(modelId)}&inst_uuid=${encodeURIComponent(uuid)}&inst_name=${encodeURIComponent(instName)}`
    : '';

  useEffect(() => {
    if (!onHeaderAction) return;
    if (loading || error || !openHref) {
      onHeaderAction(null);
      return;
    }
    onHeaderAction(
      <Button type="link" href={openHref}>
        {t('Model.openInCmdb')}
      </Button>,
    );
    return () => {
      onHeaderAction(null);
    };
  }, [error, loading, onHeaderAction, openHref, t]);

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }
  if (!propertyList.length && !Object.keys(instDetail).length) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[280px] min-w-0 flex-col gap-3">
      {!onHeaderAction && (
        <div className="flex justify-end">
          <Button type="link" href={openHref}>
            {t('Model.openInCmdb')}
          </Button>
        </div>
      )}
      <InfoList
        readOnly
        instDetail={instDetail}
        propertyList={propertyList}
        userList={userList}
      />
    </div>
  );
};

export default BaseInfoWidget;
