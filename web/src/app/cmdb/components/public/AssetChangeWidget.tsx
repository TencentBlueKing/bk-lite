'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import { LeftOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import { useChangeRecordApi, useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { publicWidgetErrorMessage } from './publicWidgetError';
import type { AttrFieldType, InstDetail } from '@/app/cmdb/types/assetManage';
import { ChangeRecordTimeline } from '@/app/cmdb/(pages)/assetData/detail/changeRecords/ChangeRecordTimeline';
import { ChangeRecordDetail } from '@/app/cmdb/(pages)/assetData/detail/changeRecords/ChangeRecordDetail';
import { buildChangeRecordDiffRows } from '@/app/cmdb/(pages)/assetData/detail/changeRecords/changeRecordDiff';
import type { ChangeRecord } from '@/app/cmdb/(pages)/assetData/detail/changeRecords/changeRecordTypes';
import {
  DEFAULT_SCENARIOS,
  filterChangeRecordsByScenarios,
  getChangeRecordRelationInfo,
} from '@/app/cmdb/(pages)/assetData/detail/changeRecords/changeRecordView';
import styles from '@/app/cmdb/(pages)/assetData/detail/changeRecords/index.module.scss';

export interface AssetChangeWidgetProps {
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
  onEmbedToolbar?: (toolbar: React.ReactNode) => void;
  objectSwitcher?: React.ReactNode;
}

function AssetChangeDetailToolbar({
  objectSwitcher,
  openHref,
  onBackToList,
}: {
  objectSwitcher?: React.ReactNode;
  openHref: string;
  onBackToList: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex w-full min-w-0 items-center gap-3">
      <Button
        type="link"
        className="h-auto shrink-0 px-0"
        icon={<LeftOutlined />}
        onClick={onBackToList}
      >
        {t('Model.changeRecord.backToTimeline')}
      </Button>
      {objectSwitcher ? (
        <div className="shrink-0">{objectSwitcher}</div>
      ) : null}
      <div className="min-w-0 flex-1" />
      {openHref ? (
        <Button type="link" className="shrink-0" href={openHref}>
          {t('Model.openInCmdb')}
        </Button>
      ) : null}
    </div>
  );
}

const AssetChangeWidget = ({
  instUuid,
  onHeaderAction,
  onEmbedToolbar,
  objectSwitcher,
}: AssetChangeWidgetProps) => {
  const { t } = useTranslation();
  const { getChangeRecords, getChangeRecordEnumData, getChangeRecordScenarioEnum } =
    useChangeRecordApi();
  const { getInstanceDetail } = useInstanceApi();
  const { getModelAttrList } = useModelApi();
  const apisRef = useRef({
    getChangeRecords,
    getChangeRecordEnumData,
    getChangeRecordScenarioEnum,
    getInstanceDetail,
    getModelAttrList,
  });
  apisRef.current = {
    getChangeRecords,
    getChangeRecordEnumData,
    getChangeRecordScenarioEnum,
    getInstanceDetail,
    getModelAttrList,
  };
  const uuid = resolveCmdbInstUuid(instUuid) || '';
  const [records, setRecords] = useState<ChangeRecord[]>([]);
  const [modelId, setModelId] = useState('');
  const [currentInstance, setCurrentInstance] = useState<Record<string, unknown>>(
    {},
  );
  const [attrList, setAttrList] = useState<AttrFieldType[]>([]);
  const [typeEnum, setTypeEnum] = useState<Record<string, string>>({});
  const [scenarioEnum, setScenarioEnum] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<number | string | null>(null);
  const [pane, setPane] = useState<'list' | 'detail'>('list');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const openHref = useMemo(() => {
    if (!uuid || !modelId) return '';
    const params = new URLSearchParams({
      inst_uuid: uuid,
      model_id: modelId,
    });
    return `/cmdb/assetData/detail/changeRecords?${params.toString()}`;
  }, [modelId, uuid]);

  useEffect(() => {
    let cancelled = false;
    if (!uuid) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setRecords([]);
      return;
    }
    setLoading(true);
    setError(null);
    setPane('list');
    const {
      getChangeRecords: fetchRecords,
      getChangeRecordEnumData: fetchTypeEnum,
      getChangeRecordScenarioEnum: fetchScenarioEnum,
      getInstanceDetail: fetchDetail,
      getModelAttrList: fetchAttrs,
    } = apisRef.current;
    fetchDetail(uuid)
      .then(async (detail: InstDetail) => {
        const nextModelId = String(detail?.model_id || '').trim();
        const [data, typeData, scenarioData, attrs] = await Promise.all([
          fetchRecords({
            inst_uuid: uuid,
            model_id: nextModelId,
          }),
          fetchTypeEnum().catch(() => ({})),
          fetchScenarioEnum().catch(() => ({})),
          nextModelId ? fetchAttrs(nextModelId).catch(() => []) : Promise.resolve([]),
        ]);
        if (cancelled) return;
        const list: ChangeRecord[] = Array.isArray(data)
          ? data
          : data?.items || [];
        setModelId(nextModelId);
        setCurrentInstance((detail || {}) as Record<string, unknown>);
        setAttrList(attrs || []);
        setTypeEnum(typeData || {});
        setScenarioEnum(scenarioData || {});
        setRecords(list);
        setPane('list');
        setSelectedId((current) =>
          list.some((item) => String(item.id) === String(current))
            ? current
            : null,
        );
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
  }, [reloadKey, t, uuid]);

  useEffect(() => {
    if (!onHeaderAction) return;
    if (pane === 'detail' || loading || error || !openHref) {
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
  }, [error, loading, onHeaderAction, openHref, pane, t]);

  useEffect(() => {
    if (!onEmbedToolbar) return;
    if (pane !== 'detail' || loading || error) {
      onEmbedToolbar(null);
      return;
    }
    onEmbedToolbar(
      <AssetChangeDetailToolbar
        objectSwitcher={objectSwitcher}
        openHref={openHref}
        onBackToList={() => setPane('list')}
      />,
    );
    return () => {
      onEmbedToolbar(null);
    };
  }, [error, loading, objectSwitcher, onEmbedToolbar, openHref, pane]);

  const visibleRecords = useMemo(
    () => filterChangeRecordsByScenarios(records, DEFAULT_SCENARIOS),
    [records],
  );
  const selectedRecord =
    visibleRecords.find((item) => String(item.id) === String(selectedId)) ||
    null;
  const attrFieldMap = useMemo(() => {
    const map: Record<string, AttrFieldType> = {};
    attrList.forEach((attr) => {
      map[attr.attr_id] = attr;
    });
    return map;
  }, [attrList]);
  const diffRows = useMemo(
    () => buildChangeRecordDiffRows(selectedRecord, currentInstance, attrFieldMap),
    [attrFieldMap, currentInstance, selectedRecord],
  );
  const relationInfo = useMemo(
    () => getChangeRecordRelationInfo(selectedRecord),
    [selectedRecord],
  );

  useEffect(() => {
    if (
      selectedId &&
      !visibleRecords.find((item) => String(item.id) === String(selectedId))
    ) {
      setSelectedId(null);
      setPane('list');
    }
  }, [selectedId, visibleRecords]);

  const scenarioLabel = (key: string) =>
    scenarioEnum[key] || t(`OperationLog.scenarioOpts.${key}`) || key;
  const typeLabel = (key: string) =>
    typeEnum[key] || t(`OperationLog.operationOpts.${key}`) || key;
  const showModelName = (id: string) => id;

  if (loading) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }
  if (!visibleRecords.length) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  const openInCmdb = openHref ? (
    <Button type="link" href={openHref}>
      {t('Model.openInCmdb')}
    </Button>
  ) : null;

  return (
    <div className="flex h-full min-h-[280px] min-w-0 flex-col gap-4">
      {pane === 'list' && !onHeaderAction ? (
        <div className="flex shrink-0 justify-end">{openInCmdb}</div>
      ) : null}
      {pane === 'detail' && !onEmbedToolbar ? (
        <div className="shrink-0">
          <AssetChangeDetailToolbar
            objectSwitcher={objectSwitcher}
            openHref={openHref}
            onBackToList={() => setPane('list')}
          />
        </div>
      ) : null}
      <div className={`${styles.changeRecords} ${styles.embedded}`}>
        {pane === 'list' ? (
          <div className={styles.timelineCol}>
            <ChangeRecordTimeline
              records={visibleRecords}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setPane('detail');
              }}
              scenarioLabel={scenarioLabel}
              typeLabel={typeLabel}
              showModelName={showModelName}
            />
          </div>
        ) : null}
        {pane === 'detail' ? (
          <div className={styles.detailCol}>
            <ChangeRecordDetail
              key={String(selectedId)}
              record={selectedRecord}
              diffRows={diffRows}
              relationInfo={relationInfo}
              scenarioLabel={scenarioLabel}
              showModelName={showModelName}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default AssetChangeWidget;
