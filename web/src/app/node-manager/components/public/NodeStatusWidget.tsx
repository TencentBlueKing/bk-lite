'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Descriptions, Spin, Tag } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useNodeApi from '@/app/node-manager/api/useNodeApi';
import {
  collectorStatusI18nKey,
  nodeOnlineI18nKey,
} from '@/app/node-manager/utils/nodeStatusDisplay';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface NodeStatusWidgetProps {
  nodeId: string;
}

interface NodeCollectorStatus {
  collector_id?: string;
  collector_name?: string;
  status?: string | number;
  message?: string;
}

interface NodeStatusPayload {
  id?: string;
  name?: string;
  ip?: string;
  active?: boolean;
  updated_at?: string;
  status?: {
    status?: string | number;
    collectors?: NodeCollectorStatus[];
  };
}

const NodeStatusWidget = ({ nodeId }: NodeStatusWidgetProps) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getNodeList } = useNodeApi();
  const getNodeListRef = useRef(getNodeList);
  getNodeListRef.current = getNodeList;
  const [node, setNode] = useState<NodeStatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const id = String(nodeId || '').trim();
    if (!id) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setNode(null);
      return;
    }
    setLoading(true);
    setError(null);
    setNode(null);
    getNodeListRef
      .current({
        page: 1,
        page_size: 1,
        filters: {
          id: [{ lookup_expr: 'exact', value: id }],
        },
      })
      .then((data: { items?: NodeStatusPayload[] }) => {
        if (cancelled) return;
        const item = data?.items?.[0] || null;
        if (!item) {
          setError(t('node-manager.cloudregion.node.publicWidgetNotFound'));
          return;
        }
        setNode(item);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
              'node-manager.cloudregion.node.publicWidgetNotFound',
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
  }, [nodeId, reloadKey, t]);

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error || !node) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error || t('common.loadFailed')} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  const collectors = node.status?.collectors || [];
  const onlineKey = nodeOnlineI18nKey(node.active);

  return (
    <div className="min-h-[280px] min-w-0">
      <Descriptions column={1} size="small">
        <Descriptions.Item label={t('node-manager.cloudregion.node.nodeName')}>
          {node.name || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('node-manager.cloudregion.node.ip')}>
          {node.ip || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('node-manager.cloudregion.node.status')}>
          {onlineKey ? t(onlineKey) : '--'}
        </Descriptions.Item>
        <Descriptions.Item
          label={t('node-manager.cloudregion.node.lastReportTime')}
        >
          {node.updated_at ? convertToLocalizedTime(node.updated_at) : '--'}
        </Descriptions.Item>
        <Descriptions.Item
          label={t('node-manager.cloudregion.node.collector')}
        >
          {collectors.length
            ? collectors.map((collector) => (
                <Tag key={`${collector.collector_id}-${collector.collector_name}`}>
                  {collector.collector_name || collector.collector_id || '--'}
                  {` (${t(collectorStatusI18nKey(collector.status))})`}
                </Tag>
            ))
            : '--'}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
};

export default NodeStatusWidget;
