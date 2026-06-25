'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { NetworkTopologyCanvas } from '@/app/cmdb/components/networkTopology';
import type {
  NetworkTopologyLayoutMode,
  NetworkTopologyLink,
  NetworkTopologyNode,
} from '@/app/cmdb/components/networkTopology';
import { useTranslation } from '@/utils/i18n';
import { useNetworkStatusTopologyApi } from '@/app/ops-analysis/api/networkStatusTopology';
import type {
  NetworkStatusTopologyLink,
  NetworkStatusTopologyNode,
  NetworkStatusTopologyResponse,
} from '@/app/ops-analysis/types/sceneWidget';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  buildAlertListUrl,
  buildFaultPath,
  buildInstanceDetailUrl,
  getLinkEndpoints,
  getLinkId,
  getNodeResource,
} from './graphModel';
import styles from './networkStatusTopology.module.scss';

interface NetworkStatusTopologyProps {
  config?: ValueConfig;
  refreshKey?: string | number;
  onReady?: (ready?: boolean) => void;
}

const stripDevicePrefix = (value?: string, deviceName?: string) => {
  if (!value) return '';
  if (deviceName && value.startsWith(`${deviceName}-`)) {
    return value.slice(deviceName.length + 1);
  }
  return value;
};

const openUrl = (url: string) => {
  window.open(url, '_blank', 'noopener,noreferrer');
};

const getStatusLabelKey = (status?: string) => {
  if (status === 'critical') return 'dashboard.networkTopoStatusCritical';
  if (status === 'error') return 'dashboard.networkTopoStatusCritical';
  if (status === 'warning') return 'dashboard.networkTopoStatusWarning';
  return 'dashboard.networkTopoStatusNormal';
};

const toCanvasNode = (
  node: NetworkStatusTopologyNode,
): NetworkTopologyNode => ({
  id: String(node.id),
  modelId: String(node.model_id),
  name: node.name || String(node.id),
  subtitle: String(node.model_id),
  hop: Number(node.hop || 0),
  status: node.status,
  alertCount: Number(node.alert_count || 0),
  pulse: Boolean(node.pulse),
  icon: typeof node.icon === 'string' ? node.icon : '',
});

const toCanvasLink = (
  link: NetworkStatusTopologyLink,
  nodeNameMap: Map<string, string>,
): NetworkTopologyLink => {
  const endpoints = getLinkEndpoints(link);
  const sourceName = nodeNameMap.get(endpoints.source);
  const targetName = nodeNameMap.get(endpoints.target);
  const sourcePort = link.source_port || link.source_inst_name;
  const targetPort = link.target_port || link.target_inst_name;

  return {
    id: getLinkId(link),
    source: endpoints.source,
    target: endpoints.target,
    sourcePort: stripDevicePrefix(sourcePort, sourceName),
    targetPort: stripDevicePrefix(targetPort, targetName),
  };
};

const NetworkStatusTopology: React.FC<NetworkStatusTopologyProps> = ({
  config,
  refreshKey,
  onReady,
}) => {
  const { t } = useTranslation();
  const { getNetworkStatusTopology } = useNetworkStatusTopologyApi();
  const [data, setData] = useState<NetworkStatusTopologyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [layoutMode, setLayoutMode] =
    useState<NetworkTopologyLayoutMode>('hierarchical');
  const [selectedNodeId, setSelectedNodeId] = useState('');

  const topoConfig = config?.networkStatusTopology;

  const fetchData = useCallback(async () => {
    if (!topoConfig?.modelId || !topoConfig?.instId) {
      setData(null);
      setError(t('dashboard.networkTopoMissingConfig'));
      onReady?.(false);
      return;
    }

    try {
      setLoading(true);
      setError('');
      const result = await getNetworkStatusTopology({
        model_id: topoConfig.modelId,
        inst_id: topoConfig.instId,
        depth: topoConfig.depth || 2,
      });
      setData(result);
      setSelectedNodeId('');
      onReady?.((result.nodes || []).length > 0);
    } catch (err) {
      console.error('network status topology fetch failed:', err);
      setData(null);
      setError(t('dashboard.networkTopoLoadFailed'));
      onReady?.(false);
    } finally {
      setLoading(false);
    }
    // API hooks return fresh function references; fetching is driven by widget config.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onReady, t, topoConfig?.depth, topoConfig?.instId, topoConfig?.modelId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData, refreshKey]);

  const originalNodeMap = useMemo(
    () =>
      new Map(
        (data?.nodes || []).map((node) => [String(node.id), node]),
      ),
    [data?.nodes],
  );

  const nodeNameMap = useMemo(
    () =>
      new Map(
        (data?.nodes || []).map((node) => [
          String(node.id),
          node.name || String(node.id),
        ]),
      ),
    [data?.nodes],
  );

  const canvasNodes = useMemo(
    () => (data?.nodes || []).map(toCanvasNode),
    [data?.nodes],
  );

  const canvasLinks = useMemo(
    () =>
      (data?.links || []).map((link) => toCanvasLink(link, nodeNameMap)),
    [data?.links, nodeNameMap],
  );

  const faultPath = useMemo(() => {
    const selected = originalNodeMap.get(selectedNodeId);
    if (!data || !selected || !selected.alert_count) {
      return { nodeIds: [], linkIds: [] };
    }
    return buildFaultPath({
      nodes: data.nodes,
      links: data.links,
      centerId: String(data.center_id),
      selectedNodeId,
    });
  }, [data, originalNodeMap, selectedNodeId]);

  const faultNodeIds = useMemo(() => new Set(faultPath.nodeIds), [faultPath.nodeIds]);
  const faultLinkIds = useMemo(() => new Set(faultPath.linkIds), [faultPath.linkIds]);
  const hasFaultPath = faultNodeIds.size > 0 || faultLinkIds.size > 0;

  const renderPopover = useCallback(
    (node: NetworkTopologyNode) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      const alertCount = Number(originalNode.alert_count || 0);
      const status = originalNode.status || 'normal';
      return (
        <div className={styles.popover}>
          <div className={styles.popHeader}>
            <span className={styles.popTitle}>{originalNode.name || node.name}</span>
            <span className={`${styles.statusPill} ${styles[status] || ''}`}>
              {t(getStatusLabelKey(status))}
            </span>
          </div>
          <div className={styles.popLine}>
            <span>{t('dashboard.networkTopoPopoverModel')}:</span>
            <strong>{String(originalNode.model_id)}</strong>
          </div>
          <div className={styles.popLine}>
            <span>{t('dashboard.networkTopoPopoverAlerts')}:</span>
            <strong className={alertCount ? styles.alertCount : styles.noAlertText}>
              {alertCount}
            </strong>
          </div>
          {originalNode.severity && (
            <div className={styles.popLine}>
              <span>{t('dashboard.networkTopoPopoverSeverity')}:</span>
              <strong>{t(getStatusLabelKey(String(originalNode.severity)))}</strong>
            </div>
          )}
        </div>
      );
    },
    [originalNodeMap, t],
  );

  const renderContextMenu = useCallback(
    (node: NetworkTopologyNode, closeMenu: () => void) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      const alertCount = Number(originalNode.alert_count || 0);
      const openInstanceDetail = () => {
        closeMenu();
        openUrl(buildInstanceDetailUrl({
          modelId: String(originalNode.model_id),
          instId: String(originalNode.id),
          instName: originalNode.name,
        }));
      };
      const openAlertList = () => {
        if (!alertCount) return;
        closeMenu();
        const resource = getNodeResource(originalNode);
        openUrl(buildAlertListUrl({
          resourceType: resource.resourceType,
          resourceId: resource.resourceId,
        }));
      };

      return (
        <div className={styles.contextMenu}>
          <button type="button" className={styles.contextMenuItem} onClick={openInstanceDetail}>
            {t('dashboard.networkTopoInstanceDetail')}
          </button>
          <button
            type="button"
            className={`${styles.contextMenuItem} ${!alertCount ? styles.disabledMenuItem : ''}`}
            disabled={!alertCount}
            onClick={openAlertList}
          >
            {t('dashboard.networkTopoViewAlerts')}
          </button>
        </div>
      );
    },
    [originalNodeMap, t],
  );

  return (
    <NetworkTopologyCanvas
      nodes={canvasNodes}
      links={canvasLinks}
      centerId={String(data?.center_id || topoConfig?.instId || '')}
      layoutMode={layoutMode}
      labels={{
        layoutHierarchical: t('dashboard.networkTopoLayoutHierarchical'),
        layoutForce: t('dashboard.networkTopoLayoutForce'),
        layoutCircular: t('dashboard.networkTopoLayoutCircular'),
        zoomOut: t('dashboard.networkTopoZoomOut'),
        zoomIn: t('dashboard.networkTopoZoomIn'),
        exportImage: t('dashboard.networkTopoExportImage'),
        refresh: t('dashboard.networkTopoRefresh'),
      }}
      selectedNodeId={selectedNodeId}
      activeNodeIds={faultNodeIds}
      activeLinkIds={faultLinkIds}
      dimInactive={hasFaultPath}
      loading={loading}
      refreshLoading={loading}
      error={error}
      emptyText={t('dashboard.networkTopoEmpty')}
      truncatedText={data?.truncated ? t('dashboard.networkTopoTruncated') : undefined}
      exportFileName="network-status-topology.svg"
      onLayoutChange={setLayoutMode}
      onRefresh={fetchData}
      onBlankClick={() => setSelectedNodeId('')}
      onNodeClick={(node) => {
        setSelectedNodeId((current) => (current === node.id ? '' : node.id));
      }}
      renderPopover={renderPopover}
      renderContextMenu={renderContextMenu}
    />
  );
};

export default NetworkStatusTopology;
