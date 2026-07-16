import React, { useEffect, useMemo, useState } from 'react';
import { Drawer, Button, Select, Space, Popconfirm, Tag, Empty, Spin } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type {
  NetworkInterfaceRef,
  NetworkInterfaceRuntime,
  NetworkPortPair,
  NetworkTopologyLink,
  NetworkTopologyNode,
} from '@/app/ops-analysis/types/networkTopology';
import { useTranslation } from '@/utils/i18n';
import { formatNetworkMetricValue } from '../utils/metricValueFormat';
import {
  DEFAULT_LINK_INTERFACE_METRICS,
  PORT_VIEW_INTERFACE_METRIC_FIELDS,
  normalizeInterfaceStatus,
  normalizeLinkInterfaceMetrics,
} from '../utils/networkTopologyUtils';

export interface NetworkEdgeDrawerProps {
  open: boolean;
  link: NetworkTopologyLink | null;
  sourceNode: NetworkTopologyNode | null;
  targetNode: NetworkTopologyNode | null;
  sourceInterfaces: NetworkInterfaceRef[];
  targetInterfaces: NetworkInterfaceRef[];
  linkRuntime?: {
    status?: 'normal' | 'critical' | 'unknown';
    interfaces?: NetworkInterfaceRuntime[];
  };
  loading?: boolean;
  loadMessage?: string | null;
  readonly?: boolean;
  /** initial port_pairs 来自父级。保存时回填到父级。 */
  onCommit: (nextPortPairs: NetworkPortPair[], interfaceMetrics: string[]) => void;
  onClose: () => void;
  zIndex?: number;
  testId?: string;
}

const interfaceOptions = (
  list: NetworkInterfaceRef[],
): Array<{ value: string; label: string }> => {
  const seen = new Set<string>();
  return list
    .filter((item) => Boolean(item.interface_name))
    .filter((item) => {
      const key = `${item.bk_inst_id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((item) => ({
      value: String(item.bk_inst_id),
      label: item.interface_name,
    }));
};

const findInterface = (
  list: NetworkInterfaceRef[],
  instId: number | string,
): NetworkInterfaceRef | undefined =>
  list.find((item) => String(item.bk_inst_id) === String(instId));

/**
 * 连线配置 Drawer(design.md §7.5):
 * - 源/目标节点只读
 * - 端口对(source + target),至少 1 对
 * - 链路运行态摘要(基于 weops batch 接口的返回)
 * - 删除连线二次确认
 */
const NetworkEdgeDrawer: React.FC<NetworkEdgeDrawerProps> = ({
  open,
  link,
  sourceNode,
  targetNode,
  sourceInterfaces,
  targetInterfaces,
  linkRuntime,
  loading = false,
  readonly = false,
  onCommit,
  onClose,
  zIndex,
  testId,
}) => {
  const { t } = useTranslation();
  const [draftPairs, setDraftPairs] = useState<NetworkPortPair[]>(
    link?.port_pairs ?? [],
  );
  const [draftInterfaceMetrics, setDraftInterfaceMetrics] = useState<string[]>(
    normalizeLinkInterfaceMetrics(link?.interface_metrics).length > 0
      ? normalizeLinkInterfaceMetrics(link?.interface_metrics)
      : DEFAULT_LINK_INTERFACE_METRICS,
  );

  useEffect(() => {
    if (!open) return;
    setDraftPairs(link?.port_pairs?.slice() ?? []);
    const savedMetrics = normalizeLinkInterfaceMetrics(link?.interface_metrics);
    setDraftInterfaceMetrics(
      savedMetrics.length > 0 ? savedMetrics : DEFAULT_LINK_INTERFACE_METRICS,
    );
  }, [open, link?.id, link?.port_pairs, link?.interface_metrics]);

  const metricLabels = useMemo<Record<string, string>>(
    () => ({
      ifInOctets_5min: t('opsAnalysis.networkTopology.link.metricIfInOctets'),
      ifOutOctets_5min: t('opsAnalysis.networkTopology.link.metricIfOutOctets'),
      ifHighSpeed: t('opsAnalysis.networkTopology.link.metricIfHighSpeed'),
      ifOutDiscards_5min: t('opsAnalysis.networkTopology.link.metricIfOutDiscards'),
      ifInDiscards_5min: t('opsAnalysis.networkTopology.link.metricIfInDiscards'),
      ifInErrors_5min: t('opsAnalysis.networkTopology.link.metricIfInErrors'),
      ifOutErrors_5min: t('opsAnalysis.networkTopology.link.metricIfOutErrors'),
    }),
    [t],
  );
  const interfaceMetricOptions = useMemo(
    () =>
      PORT_VIEW_INTERFACE_METRIC_FIELDS.map((field) => ({
        value: field,
        label: metricLabels[field] ?? field,
      })),
    [metricLabels],
  );

  if (!link) {
    return (
      <Drawer
        open={open}
        onClose={onClose}
        width={520}
        zIndex={zIndex}
        title={t('opsAnalysis.networkTopology.link.drawerTitle')}
        destroyOnClose
        data-testid={testId ?? 'network-edge-drawer'}
      >
        <Empty description={t('opsAnalysis.networkTopology.link.emptySelection')} />
      </Drawer>
    );
  }

  const canSave =
    !loading &&
    draftPairs.length > 0 &&
    draftPairs.every((pair) => pair.source_interface.bk_inst_id && pair.target_interface.bk_inst_id);
  const status = linkRuntime?.status ?? 'unknown';

  const updatePair = (index: number, partial: Partial<NetworkPortPair>) => {
    setDraftPairs((prev) =>
      prev.map((pair, i) => (i === index ? { ...pair, ...partial } : pair)),
    );
  };

  const addPair = () => {
    setDraftPairs((prev) => [
      ...prev,
      {
        source_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 0, interface_name: '' },
        target_interface: { bk_obj_id: 'bk_interface', bk_inst_id: 0, interface_name: '' },
      },
    ]);
  };

  const removePair = (index: number) => {
    setDraftPairs((prev) => prev.filter((_, i) => i !== index));
  };

  const statusLabelKey =
    status === 'critical'
      ? 'opsAnalysis.networkTopology.link.statusCritical'
      : status === 'normal'
        ? 'opsAnalysis.networkTopology.link.statusNormal'
        : 'opsAnalysis.networkTopology.link.statusUnknown';

  const drawerTitle =
    sourceNode && targetNode
      ? t('opsAnalysis.networkTopology.link.drawerTitleWithNodes', undefined, {
        source: sourceNode.bk_inst_name,
        target: targetNode.bk_inst_name,
      })
      : t('opsAnalysis.networkTopology.link.drawerTitle');
  const detailTitle =
    sourceNode && targetNode
      ? t('opsAnalysis.networkTopology.link.detailTitleWithNodes', undefined, {
        source: sourceNode.bk_inst_name,
        target: targetNode.bk_inst_name,
      })
      : t('opsAnalysis.networkTopology.link.detailTitle');
  const statusTag = (
    <Tag
      color={status === 'critical' ? 'red' : status === 'normal' ? 'green' : 'default'}
      data-testid="network-edge-drawer-status"
    >
      {t(statusLabelKey)}
    </Tag>
  );
  const infoRows = [
    {
      label: t('opsAnalysis.networkTopology.link.runtimeStatus'),
      value: statusTag,
    },
    {
      label: t('opsAnalysis.networkTopology.link.labelPairCount'),
      value: t('opsAnalysis.networkTopology.link.pairCount', undefined, {
        count: draftPairs.length,
      }),
    },
    {
      label: t('opsAnalysis.networkTopology.link.labelSourceNode'),
      value: sourceNode?.bk_inst_name ?? '--',
    },
    {
      label: t('opsAnalysis.networkTopology.link.labelTargetNode'),
      value: targetNode?.bk_inst_name ?? '--',
    },
    {
      label: t('opsAnalysis.networkTopology.link.labelSourceInterfaces'),
      value: t('opsAnalysis.networkTopology.link.interfaceCountShort', undefined, {
        count: sourceInterfaces.length,
      }),
    },
    {
      label: t('opsAnalysis.networkTopology.link.labelTargetInterfaces'),
      value: t('opsAnalysis.networkTopology.link.interfaceCountShort', undefined, {
        count: targetInterfaces.length,
      }),
    },
  ];
  const infoLabelStyle: React.CSSProperties = {
    padding: '9px 12px',
    borderRight: '1px solid #e5e9ef',
    borderBottom: '1px solid #e5e9ef',
    background: '#f7f9fc',
    color: '#5f7290',
    fontSize: 12,
    width: 112,
  };
  const infoValueStyle: React.CSSProperties = {
    padding: '9px 14px 9px 18px',
    borderRight: '1px solid #e5e9ef',
    borderBottom: '1px solid #e5e9ef',
    color: '#1f2933',
    fontSize: 12,
    minWidth: 0,
  };
  const portStatusColor = (value: ReturnType<typeof normalizeInterfaceStatus>) => {
    if (value === 'up') return 'green';
    if (value === 'down') return 'red';
    if (value === 'testing') return 'blue';
    return 'default';
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={620}
      zIndex={zIndex}
      destroyOnClose
      title={readonly ? detailTitle : drawerTitle}
      data-testid={testId ?? 'network-edge-drawer'}
      footer={
        readonly ? (
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button onClick={onClose}>{t('opsAnalysis.networkTopology.actions.close')}</Button>
          </div>
        ) : (
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Space>
            <Button onClick={onClose}>{t('opsAnalysis.networkTopology.actions.cancel')}</Button>
            <Button
              type="primary"
              disabled={readonly || loading || !canSave}
              data-testid="network-edge-drawer-save"
              onClick={() => {
                onCommit(
                  draftPairs
                    .filter((p) => p.source_interface.bk_inst_id && p.target_interface.bk_inst_id)
                    .map((p) => ({
                      source_interface: { ...p.source_interface },
                      target_interface: { ...p.target_interface },
                    })),
                  normalizeLinkInterfaceMetrics(draftInterfaceMetrics),
                );
                onClose();
              }}
            >
              {t('opsAnalysis.networkTopology.actions.confirm')}
            </Button>
            </Space>
          </div>
        )
      }
    >
      <div
        style={{
          border: '1px solid #e0e7ee',
          borderRadius: 8,
          overflow: 'hidden',
          background: '#fff',
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '104px minmax(0, 1fr) 104px minmax(0, 1fr)',
          }}
        >
          {infoRows.map((row, index) => (
            <React.Fragment key={`${row.label}-${index}`}>
              <div style={infoLabelStyle}>{row.label}</div>
              <div style={infoValueStyle}>{row.value}</div>
            </React.Fragment>
          ))}
        </div>
      </div>

      <Space direction="vertical" size={8} style={{ marginTop: 12, width: '100%' }}>
        <div
          style={{
            padding: 10,
            border: '1px solid #e0e7ee',
            borderRadius: 8,
            background: '#f8fafb',
          }}
        >
          <div style={{ marginBottom: 6, color: '#334250', fontSize: 13, fontWeight: 600 }}>
            {t('opsAnalysis.networkTopology.link.interfaceMetricsTitle')}
          </div>
          <Select
            mode="multiple"
            allowClear
            style={{ width: '100%' }}
            placeholder={t('opsAnalysis.networkTopology.link.interfaceMetricsPlaceholder')}
            options={interfaceMetricOptions}
            value={draftInterfaceMetrics}
            disabled={readonly || loading}
            onChange={(values) => setDraftInterfaceMetrics(normalizeLinkInterfaceMetrics(values))}
            getPopupContainer={(trigger) =>
              trigger.parentElement ?? document.body
            }
            data-testid="network-edge-drawer-interface-metrics"
          />
        </div>
        {loading && (
          <div
            style={{
              padding: '18px 12px',
              border: '1px solid #e0e7ee',
              borderRadius: 8,
              background: '#f8fafb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              color: '#64748b',
            }}
            data-testid="network-edge-drawer-loading"
          >
            <Spin size="small" />
            <span>{t('opsAnalysis.networkTopology.link.loadingInterfaces')}</span>
          </div>
        )}
        {!loading && draftPairs.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('opsAnalysis.networkTopology.link.noPortPairs')}
          />
        )}
        {draftPairs.map((pair, index) => (
          <div
            key={`pair-${index}`}
            style={{
              padding: 10,
              border: '1px solid #e0e7ee',
              borderRadius: 8,
              background: '#f8fafb',
              display: 'flex',
              gap: 8,
              alignItems: 'center',
            }}
            data-testid="network-edge-drawer-pair-row"
          >
            <Select
              style={{ flex: 1 }}
              placeholder={t('opsAnalysis.networkTopology.link.labelSourcePort')}
              options={interfaceOptions(sourceInterfaces)}
              getPopupContainer={(trigger) =>
                trigger.parentElement ?? document.body
              }
              value={pair.source_interface.bk_inst_id ? String(pair.source_interface.bk_inst_id) : undefined}
              onChange={(instId) => {
                const found = findInterface(sourceInterfaces, Number(instId));
                if (found) updatePair(index, { source_interface: found });
              }}
              disabled={readonly || loading}
              data-testid={`network-edge-drawer-source-select-${index}`}
            />
            <span style={{ color: '#94a3b8' }}>→</span>
            <Select
              style={{ flex: 1 }}
              placeholder={t('opsAnalysis.networkTopology.link.labelTargetPort')}
              options={interfaceOptions(targetInterfaces)}
              getPopupContainer={(trigger) =>
                trigger.parentElement ?? document.body
              }
              value={pair.target_interface.bk_inst_id ? String(pair.target_interface.bk_inst_id) : undefined}
              onChange={(instId) => {
                const found = findInterface(targetInterfaces, Number(instId));
                if (found) updatePair(index, { target_interface: found });
              }}
              disabled={readonly || loading}
              data-testid={`network-edge-drawer-target-select-${index}`}
            />
            <Popconfirm
              title={t('opsAnalysis.networkTopology.link.removePortPairTitle')}
              okText={t('opsAnalysis.networkTopology.actions.delete')}
              cancelText={t('opsAnalysis.networkTopology.actions.cancel')}
              okButtonProps={{ danger: true }}
              disabled={readonly || loading}
              onConfirm={() => removePair(index)}
            >
              <Button danger type="text" icon={<DeleteOutlined />} disabled={readonly || loading} />
            </Popconfirm>
          </div>
        ))}
      </Space>

      {!readonly && (
        <Button
          icon={<PlusOutlined />}
          type="dashed"
          style={{ marginTop: 12 }}
          onClick={addPair}
          disabled={loading}
          data-testid="network-edge-drawer-add-pair"
        >
          {t('opsAnalysis.networkTopology.link.addPortPair')}
        </Button>
      )}

      {linkRuntime?.interfaces && linkRuntime.interfaces.length > 0 && (
        <div
          style={{
            marginTop: 18,
            padding: 12,
            border: '1px solid #e0e7ee',
            borderRadius: 8,
            background: '#f8fafc',
          }}
          data-testid="network-edge-drawer-runtime"
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 10,
            }}
          >
            <strong style={{ fontSize: 13, color: '#1f2933' }}>
              {t('opsAnalysis.networkTopology.link.runtimeSummary')}
            </strong>
            <span style={{ fontSize: 12, color: '#64748b' }}>
              {t('opsAnalysis.networkTopology.link.interfaceCountShort', undefined, {
                count: linkRuntime.interfaces.length,
              })}
            </span>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gap: 8,
            }}
          >
            {linkRuntime.interfaces.map((iface, idx) => {
              const admin = normalizeInterfaceStatus(iface.admin_status);
              const oper = normalizeInterfaceStatus(iface.oper_status);
              const name =
                (iface as { interface_name?: string }).interface_name ??
                iface.source_interface?.interface_name ??
                '-';
              return (
                <div
                  key={idx}
                  style={{
                    minWidth: 0,
                    padding: '9px 10px',
                    border: '1px solid #e0e7ee',
                    borderRadius: 6,
                    background: '#fff',
                  }}
                >
                  <div
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontSize: 12,
                      fontWeight: 600,
                      color: '#1f2933',
                    }}
                    title={name}
                  >
                    {name}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 6,
                      marginTop: 7,
                    }}
                  >
                    <Tag color={portStatusColor(admin)} style={{ marginInlineEnd: 0 }}>
                      admin {admin}
                    </Tag>
                    <Tag color={portStatusColor(oper)} style={{ marginInlineEnd: 0 }}>
                      oper {oper}
                    </Tag>
                  </div>
                  {draftInterfaceMetrics.length > 0 && (
                    <div style={{ marginTop: 8, display: 'grid', gap: 5 }}>
                      {draftInterfaceMetrics.map((field) => {
                        const metric = iface.metrics?.[field];
                        const value =
                          metric && metric.value !== null && metric.value !== undefined
                            ? formatNetworkMetricValue(metric.value, metric.unit)
                            : '--';
                        return (
                          <div
                            key={field}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              gap: 10,
                              fontSize: 12,
                            }}
                          >
                            <span
                              style={{
                                minWidth: 0,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                color: '#64748b',
                              }}
                            >
                              {metricLabels[field] ?? field}
                            </span>
                            <span style={{ flexShrink: 0, color: '#1f2933', fontWeight: 600 }}>
                              {value}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Drawer>
  );
};

export default NetworkEdgeDrawer;
