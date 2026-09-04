'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Progress,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleFilled,
  ClusterOutlined,
  DatabaseOutlined,
  ExportOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import ExecutionStatusBadge from '@/components/execution-status-badge';
import CompactEmptyState from '@/components/compact-empty-state';
import PermissionWrapper from '@/components/permission';
import { useOidApi, usePortFingerprintApi, useScanApi } from '@/app/cmdb/api';
import { getNetworkDeviceOptions } from '@/app/cmdb/constants/professCollection';
import { useTranslation } from '@/utils/i18n';
import { isScanExecutionBusy } from './scanExecutionStatus';
import { SCAN_FAMILIES } from './ScanTaskDrawer';

export interface ScanExecutionSummary {
  id: number;
  status: string;
  target_count: number;
  received_count: number;
}

export interface ScanHitItem {
  id: number;
  host: string;
  protocol: string;
  family_model_id?: string;
  status: string;
  soid: string;
  cmdb_model_id: string;
  credential_id: string;
  credential_label?: string;
  inst_uuid: string;
  port?: number;
  unmatch_reason?: string;
  snapshot?: Record<string, unknown>;
}

interface ScanHitsDrawerProps {
  open: boolean;
  execution?: ScanExecutionSummary | null;
  onClose: () => void;
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'timed_out']);
const HIT_FETCH_SIZE = 200;
const TABLE_PAGE_SIZE = 20;
const GROUP_PAGE_SIZE = 10;
const SOID_LIBRARY_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';
const PORT_LIBRARY_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/port';
const SCAN_PERMISSION_PATH = '/cmdb/assetManage/autoDiscovery/collection';
const EMPTY_SOID_KEY = '__empty_soid__';

const displayValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  return String(value);
};

const snapshotText = (hit: ScanHitItem, keys: string[]) => {
  const snapshot = hit.snapshot || {};
  for (const key of keys) {
    const value = snapshot[key];
    if (value !== null && value !== undefined && value !== '') {
      return String(value);
    }
  }
  return '--';
};

const hitSoid = (hit: ScanHitItem) => {
  const fromField = String(hit.soid || '').trim();
  if (fromField) {
    return fromField;
  }
  const snapshot = hit.snapshot || {};
  for (const key of ['soid', 'sysobjectid', 'sysObjectID']) {
    const value = snapshot[key];
    if (value !== null && value !== undefined && value !== '') {
      return String(value).trim();
    }
  }
  return '';
};

const oidLibraryUrl = (soid: string) => `${SOID_LIBRARY_PATH}?oid=${encodeURIComponent(soid)}`;
const portLibraryUrl = (targetType: string) =>
  `${PORT_LIBRARY_PATH}?type=${encodeURIComponent(targetType)}`;

const DEVICE_TYPE_ICONS: Record<string, React.ReactNode> = {
  switch: <BranchesOutlined className="text-xl" />,
  router: <ApiOutlined className="text-xl" />,
  firewall: <SafetyCertificateOutlined className="text-xl" />,
  loadbalance: <ClusterOutlined className="text-xl" />,
};

const UnmatchedGroupTable: React.FC<{
  columns: Array<Record<string, unknown>>;
  hits: ScanHitItem[];
  selectedHitIds: number[];
  onSelectedChange: (nextIds: number[], visibleIds: number[]) => void;
}> = ({ columns, hits, selectedHitIds, onSelectedChange }) => {
  const [page, setPage] = useState(1);
  const pagedHits = useMemo(() => {
    const start = (page - 1) * TABLE_PAGE_SIZE;
    return hits.slice(start, start + TABLE_PAGE_SIZE);
  }, [hits, page]);

  return (
    <div>
      <CustomTable
        rowKey="id"
        columns={columns}
        dataSource={pagedHits}
        rowSelection={{
          selectedRowKeys: selectedHitIds,
          onChange: (keys) =>
            onSelectedChange(
              keys as number[],
              pagedHits.map((item) => item.id)
            ),
        }}
        pagination={false}
      />
      {hits.length > TABLE_PAGE_SIZE ? (
        <div className="flex justify-end p-2.5">
          <Pagination
            size="small"
            current={page}
            pageSize={TABLE_PAGE_SIZE}
            total={hits.length}
            showSizeChanger={false}
            onChange={(next) => setPage(next)}
          />
        </div>
      ) : null}
    </div>
  );
};

const ScanHitsDrawer: React.FC<ScanHitsDrawerProps> = ({ open, execution, onClose }) => {
  const { t } = useTranslation();
  const {
    getScanExecution,
    getScanHits,
    generateCollect,
    pushMonitor,
    classifyHits,
    rematchSoid,
  } = useScanApi();
  const { createOid } = useOidApi();
  const { createPortFingerprint } = usePortFingerprintApi();

  const deviceTypeList = useMemo(() => getNetworkDeviceOptions(t), [t]);
  const [activeExecution, setActiveExecution] = useState<ScanExecutionSummary | null>(execution || null);
  const [hits, setHits] = useState<ScanHitItem[]>([]);
  const [hitTotal, setHitTotal] = useState(0);
  const [hitsLoading, setHitsLoading] = useState(false);
  const [selectedHitIds, setSelectedHitIds] = useState<number[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [topTab, setTopTab] = useState('matched');
  const [familyTab, setFamilyTab] = useState('network');
  const [matchedPage, setMatchedPage] = useState(1);
  const [networkGroupPage, setNetworkGroupPage] = useState(1);
  const [dbGroupPage, setDbGroupPage] = useState(1);

  // SOID 指纹弹窗
  const [fingerprintOpen, setFingerprintOpen] = useState(false);
  const [fingerprintSoid, setFingerprintSoid] = useState('');
  const [fingerprintHitIds, setFingerprintHitIds] = useState<number[]>([]);
  const [fingerprintOidLocked, setFingerprintOidLocked] = useState(true);
  const [fingerprintSaving, setFingerprintSaving] = useState(false);

  // 端口指纹弹窗
  const [portFingerprintOpen, setPortFingerprintOpen] = useState(false);
  const [portFingerprintType, setPortFingerprintType] = useState('');
  const [portFingerprintSaving, setPortFingerprintSaving] = useState(false);

  // 快捷选类型弹窗（网络未匹配）
  const [classifyOpen, setClassifyOpen] = useState(false);
  const [classifyKind, setClassifyKind] = useState<'collect' | 'monitor'>('monitor');
  const [pendingUnmatchedIds, setPendingUnmatchedIds] = useState<number[]>([]);
  const [pendingValidExportIds, setPendingValidExportIds] = useState<number[]>([]);

  const [fingerprintForm] = Form.useForm();
  const [portFingerprintForm] = Form.useForm();
  const [classifyForm] = Form.useForm();

  const selectedModelId = Form.useWatch('cmdb_model_id', classifyForm);
  const selectedFingerprintType = Form.useWatch('device_type', fingerprintForm);

  const statusLabel = useMemo(
    () => ({
      pending: t('Scan.statusPending'),
      running: t('Scan.statusRunning'),
      finalizing: t('Scan.statusFinalizing'),
      completed: t('Scan.statusCompleted'),
      failed: t('Scan.statusFailed'),
      timed_out: t('Scan.statusTimedOut'),
    }),
    [t]
  );

  const familyLabel = useCallback(
    (modelId: string) => {
      if (modelId === 'database') return t('Scan.familyDatabase');
      if (modelId === 'mysql') return t('Scan.familyMysql');
      if (modelId === 'postgresql') return t('Scan.familyPostgresql');
      if (modelId === 'mssql') return t('Scan.familyMssql');
      const family = SCAN_FAMILIES.find((item) => item.modelId === modelId);
      return family ? t(family.labelKey) : modelId;
    },
    [t]
  );

  const fetchAllHits = useCallback(
    async (executionId: number, options?: { silent?: boolean }) => {
      const silent = Boolean(options?.silent);
      if (!silent) {
        setHitsLoading(true);
      }
      try {
        const executionDetail = await getScanExecution(executionId);
        setActiveExecution({
          id: executionDetail.id,
          status: executionDetail.status,
          target_count: executionDetail.target_count,
          received_count: executionDetail.received_count,
        });
        const collected: ScanHitItem[] = [];
        let page = 1;
        let total = 0;
        while (true) {
          const hitPageData = await getScanHits(executionId, { page, page_size: HIT_FETCH_SIZE });
          const items = hitPageData.items || [];
          total = hitPageData.count || 0;
          collected.push(...items);
          if (collected.length >= total || items.length === 0) {
            break;
          }
          page += 1;
        }
        setHits(collected);
        setHitTotal(total);
      } finally {
        if (!silent) {
          setHitsLoading(false);
        }
      }
    },
    [getScanExecution, getScanHits]
  );

  useEffect(() => {
    if (!open || !execution?.id) {
      return;
    }
    setSelectedHitIds([]);
    setTopTab('matched');
    setMatchedPage(1);
    setNetworkGroupPage(1);
    setDbGroupPage(1);
    fetchAllHits(execution.id).catch((error) => {
      console.error(error);
      message.error(t('Scan.noHits'));
    });
  }, [open, execution?.id]);

  useEffect(() => {
    if (!open || !activeExecution || !isScanExecutionBusy(activeExecution.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchAllHits(activeExecution.id, { silent: true }).catch((error) => console.error(error));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeExecution, fetchAllHits, open]);

  const canSplitUnmatched = Boolean(activeExecution && TERMINAL_STATUSES.has(activeExecution.status));

  const matchedHits = useMemo(() => {
    if (!canSplitUnmatched) {
      return hits;
    }
    return hits.filter((hit) => !hit.unmatch_reason);
  }, [canSplitUnmatched, hits]);

  const unmatchedHits = useMemo(() => {
    if (!canSplitUnmatched) {
      return [];
    }
    return hits.filter((hit) => Boolean(hit.unmatch_reason));
  }, [canSplitUnmatched, hits]);

  // 网络未匹配行（未匹配且非数据库鉴权失败）
  const networkUnmatchedHits = useMemo(() => {
    return unmatchedHits.filter((hit) => hit.unmatch_reason !== 'credential_failed');
  }, [unmatchedHits]);

  // 数据库未匹配行（credential_failed）
  const dbUnmatchedHits = useMemo(() => {
    return unmatchedHits.filter((hit) => hit.unmatch_reason === 'credential_failed');
  }, [unmatchedHits]);

  const matchedFamilies = useMemo(() => {
    const order = ['network', 'host', 'physcial_server', 'database', 'mysql', 'postgresql', 'mssql', 'influxdb'];
    const present = new Set(matchedHits.map((hit) => hit.family_model_id || hit.protocol || 'unknown'));
    return [...present].sort((a, b) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [matchedHits]);

  useEffect(() => {
    if (!matchedFamilies.length) {
      return;
    }
    if (!matchedFamilies.includes(familyTab)) {
      setFamilyTab(matchedFamilies[0]);
      setMatchedPage(1);
    }
  }, [familyTab, matchedFamilies]);

  const familyHits = useMemo(
    () => matchedHits.filter((hit) => (hit.family_model_id || hit.protocol) === familyTab),
    [familyTab, matchedHits]
  );

  // 网络未匹配按 SOID 分组
  const networkUnmatchedGroups = useMemo(() => {
    const grouped = new Map<string, ScanHitItem[]>();
    networkUnmatchedHits.forEach((hit) => {
      const key = hitSoid(hit) || EMPTY_SOID_KEY;
      const list = grouped.get(key) || [];
      list.push(hit);
      grouped.set(key, list);
    });
    return [...grouped.entries()]
      .sort((a, b) => {
        if (a[0] === EMPTY_SOID_KEY) return 1;
        if (b[0] === EMPTY_SOID_KEY) return -1;
        return b[1].length - a[1].length;
      })
      .map(([soid, groupHits]) => ({ soid, hits: groupHits }));
  }, [networkUnmatchedHits]);

  // 数据库未匹配按 family_model_id 分组
  const dbUnmatchedGroups = useMemo(() => {
    const grouped = new Map<string, ScanHitItem[]>();
    dbUnmatchedHits.forEach((hit) => {
      const key = hit.family_model_id || hit.protocol || 'database';
      const list = grouped.get(key) || [];
      list.push(hit);
      grouped.set(key, list);
    });
    return [...grouped.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .map(([familyModelId, groupHits]) => ({ familyModelId, hits: groupHits }));
  }, [dbUnmatchedHits]);

  const pagedFamilyHits = useMemo(() => {
    const start = (matchedPage - 1) * TABLE_PAGE_SIZE;
    return familyHits.slice(start, start + TABLE_PAGE_SIZE);
  }, [familyHits, matchedPage]);

  const pagedNetworkGroups = useMemo(() => {
    const start = (networkGroupPage - 1) * GROUP_PAGE_SIZE;
    return networkUnmatchedGroups.slice(start, start + GROUP_PAGE_SIZE);
  }, [networkGroupPage, networkUnmatchedGroups]);

  const pagedDbGroups = useMemo(() => {
    const start = (dbGroupPage - 1) * GROUP_PAGE_SIZE;
    return dbUnmatchedGroups.slice(start, start + GROUP_PAGE_SIZE);
  }, [dbGroupPage, dbUnmatchedGroups]);

  const selectedSet = useMemo(() => new Set(selectedHitIds), [selectedHitIds]);

  const toggleRows = (ids: number[], checked: boolean) => {
    setSelectedHitIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, ...ids]));
      }
      return prev.filter((id) => !ids.includes(id));
    });
  };

  const handleBatchResult = (
    kind: 'collect' | 'monitor',
    result: Record<string, number> & { items?: Array<{ status?: string; reason?: string; host?: string }> }
  ) => {
    if (kind === 'collect') {
      const created = result?.created ?? 0;
      const appended = result?.appended ?? 0;
      const skipped = result?.skipped ?? 0;
      const failed = result?.failed ?? 0;
      if (failed || skipped || appended || created === 0) {
        message.warning(t('Scan.generateCollectPartial', undefined, { created, appended, skipped, failed }));
      } else {
        message.success(t('Scan.generateCollectDone', undefined, { count: created }));
      }
      return;
    }
    const pushed = result?.pushed ?? 0;
    const failed = result?.failed ?? 0;
    const skipped = result?.skipped ?? 0;
    const items = Array.isArray(result?.items) ? result.items : [];
    const reasons = items
      .filter((item) => item.status !== 'pushed' && item.reason)
      .slice(0, 3)
      .map((item) => `${item.host || '-'}: ${item.reason}`)
      .join('；');
    if (failed || skipped || pushed === 0) {
      const summary = t('Scan.pushMonitorPartial', undefined, { pushed, failed, skipped });
      message.warning(reasons ? `${summary}（${reasons}）` : summary);
    } else {
      message.success(t('Scan.pushMonitorDone', undefined, { count: pushed }));
    }
  };

  const runExport = async (kind: 'collect' | 'monitor', hitIds: number[]) => {
    if (!activeExecution?.id || !hitIds.length) {
      return;
    }
    if (kind === 'collect') {
      const result = await generateCollect(activeExecution.id, hitIds);
      handleBatchResult('collect', result);
    } else {
      const result = await pushMonitor(activeExecution.id, hitIds);
      handleBatchResult('monitor', result);
    }
  };

  const handleBatch = async (kind: 'collect' | 'monitor') => {
    if (!activeExecution?.id) {
      return;
    }
    if (!selectedHitIds.length) {
      message.warning(t('Scan.selectHits'));
      return;
    }

    const selectedHits = hits.filter((item) => selectedHitIds.includes(item.id));
    const dbUnmatchedSelected = selectedHits.filter((item) => item.unmatch_reason === 'credential_failed');
    const networkUnmatchedSelected = selectedHits.filter(
      (item) => item.unmatch_reason && item.unmatch_reason !== 'credential_failed'
    );
    const matchedSelected = selectedHits.filter((item) => !item.unmatch_reason);

    // 若只勾选了数据库未匹配项
    if (dbUnmatchedSelected.length > 0 && networkUnmatchedSelected.length === 0 && matchedSelected.length === 0) {
      message.warning(t('Scan.dbUnmatchedOnlyCreateCi'));
      return;
    }

    // 过滤掉数据库未匹配项
    const validExportHits = [...networkUnmatchedSelected, ...matchedSelected];
    const validExportIds = validExportHits.map((item) => item.id);

    if (networkUnmatchedSelected.length > 0) {
      if (!canSplitUnmatched) {
        message.warning(t('Scan.awaitingFinalize'));
        return;
      }
      setClassifyKind(kind);
      setPendingUnmatchedIds(networkUnmatchedSelected.map((item) => item.id));
      setPendingValidExportIds(validExportIds);
      classifyForm.setFieldsValue({ cmdb_model_id: undefined });
      setClassifyOpen(true);
      return;
    }

    setBatchLoading(true);
    try {
      await runExport(kind, validExportIds);
    } catch (error) {
      console.error(error);
      message.error(kind === 'collect' ? t('Scan.generateCollectFailed') : t('Scan.pushMonitorFailed'));
    } finally {
      setBatchLoading(false);
    }
  };

  const confirmClassify = async () => {
    if (!activeExecution?.id) {
      return;
    }
    const values = await classifyForm.validateFields();
    setBatchLoading(true);
    try {
      await classifyHits(activeExecution.id, pendingUnmatchedIds, values.cmdb_model_id);
      await runExport(classifyKind, pendingValidExportIds);
      setClassifyOpen(false);
      await fetchAllHits(activeExecution.id, { silent: true });
    } catch (error) {
      console.error(error);
      message.error(classifyKind === 'collect' ? t('Scan.generateCollectFailed') : t('Scan.pushMonitorFailed'));
    } finally {
      setBatchLoading(false);
    }
  };

  // 网络设备 SOID 指纹弹窗
  const openFingerprint = (soid: string, hitIds: number[]) => {
    const locked = Boolean(soid);
    setFingerprintSoid(soid);
    setFingerprintHitIds(hitIds);
    setFingerprintOidLocked(locked);
    fingerprintForm.setFieldsValue({
      oid: soid,
      device_type: undefined,
      brand: '',
      model: '',
    });
    setFingerprintOpen(true);
  };

  const confirmFingerprint = async () => {
    if (!activeExecution?.id) {
      return;
    }
    const values = await fingerprintForm.validateFields();
    const oid = String(values.oid || fingerprintSoid || '').trim();
    setFingerprintSaving(true);
    try {
      try {
        await createOid({
          oid,
          device_type: values.device_type,
          brand: values.brand,
          model: values.model,
        });
        message.success(t('Scan.fingerprintSaved'));
      } catch (error) {
        const text = error instanceof Error ? error.message : String(error);
        if (!text.includes('已存在') && !text.toLowerCase().includes('already')) {
          throw error;
        }
      }
      const result = await rematchSoid(activeExecution.id, oid, fingerprintHitIds);
      const classified = result?.classified ?? 0;
      if (classified) {
        message.success(t('Scan.fingerprintRematchDone', undefined, { count: classified }));
      } else {
        message.warning(t('Scan.fingerprintRematchEmpty'));
      }
      setFingerprintOpen(false);
      await fetchAllHits(activeExecution.id, { silent: true });
    } catch (error) {
      console.error(error);
    } finally {
      setFingerprintSaving(false);
    }
  };

  // 数据库端口指纹弹窗
  const openPortFingerprint = (familyModelId: string) => {
    setPortFingerprintType(familyModelId);
    portFingerprintForm.resetFields();
    portFingerprintForm.setFieldsValue({
      target_type: familyModelId,
      protocol: 'tcp',
      port: undefined,
    });
    setPortFingerprintOpen(true);
  };

  const confirmPortFingerprint = async () => {
    const values = await portFingerprintForm.validateFields();
    setPortFingerprintSaving(true);
    try {
      await createPortFingerprint({
        port: Number(values.port),
        target_type: portFingerprintType,
        protocol: 'tcp',
      });
      message.success(t('Scan.portFingerprintSaved'));
      setPortFingerprintOpen(false);
    } catch (error: any) {
      const text = error instanceof Error ? error.message : String(error);
      if (text.includes('已存在') || text.toLowerCase().includes('already')) {
        message.warning(t('Scan.portFingerprintSaved'));
        setPortFingerprintOpen(false);
      } else {
        message.error(error?.message || t('OidLibrary.operateFailed'));
      }
    } finally {
      setPortFingerprintSaving(false);
    }
  };

  const renderHost = (_: unknown, record: ScanHitItem) => (
    <span className="font-mono font-medium text-[var(--color-text-1)]">{record.host || '--'}</span>
  );

  const renderCredential = (_: unknown, record: ScanHitItem) => {
    const label = record.credential_label || record.credential_id;
    if (!label) return '--';
    return (
      <Tag className="!m-0 !rounded !border-[var(--color-border-2)] !bg-[var(--color-fill-1)] !px-1.5 !text-xs !text-[var(--color-text-2)]">
        {label}
      </Tag>
    );
  };

  const matchedColumns = useMemo(() => {
    const hostCol = { title: t('Scan.host'), dataIndex: 'host', key: 'host', render: renderHost };
    const credentialCol = {
      title: t('Scan.credential'),
      key: 'credential',
      render: renderCredential,
    };
    if (familyTab === 'host') {
      return [
        hostCol,
        {
          title: t('Scan.hostname'),
          key: 'hostname',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['hostname']),
        },
        {
          title: t('Scan.osType'),
          key: 'osType',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['os_type']),
        },
        {
          title: t('Scan.osName'),
          key: 'osName',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['os_name']),
        },
        {
          title: t('Scan.osVersion'),
          key: 'osVersion',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['os_version']),
        },
        credentialCol,
      ];
    }
    if (familyTab === 'physcial_server') {
      return [
        hostCol,
        {
          title: t('Scan.serialNumber'),
          key: 'serial',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['serial_number']),
        },
        {
          title: t('Scan.uuid'),
          key: 'uuid',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['uuid']),
        },
        {
          title: t('Scan.model'),
          dataIndex: 'cmdb_model_id',
          key: 'cmdb_model_id',
          render: (value: string) => value || '--',
        },
        credentialCol,
      ];
    }
    if (familyTab === 'network') {
      return [
        hostCol,
        {
          title: t('Scan.sysname'),
          key: 'sysname',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['sysname', 'inst_name']),
        },
        {
          title: t('Scan.deviceType'),
          key: 'deviceType',
          render: (_: unknown, record: ScanHitItem) => (
            <Tag className="!m-0 !rounded !border-0 !bg-[color-mix(in_srgb,var(--color-primary)_10%,transparent)] !px-1.5 !text-xs !text-[var(--color-primary)]">
              {record.cmdb_model_id || snapshotText(record, ['device_type'])}
            </Tag>
          ),
        },
        {
          title: t('Scan.brand'),
          key: 'brand',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['brand']),
        },
        {
          title: t('Scan.modelName'),
          key: 'modelName',
          render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['model']),
        },
        {
          title: t('Scan.soid'),
          key: 'soid',
          render: (_: unknown, record: ScanHitItem) => {
            const val = hitSoid(record);
            return val ? <span className="font-mono text-xs text-[var(--color-text-2)]">{val}</span> : '--';
          },
        },
        credentialCol,
      ];
    }
    return [
      hostCol,
      {
        title: t('Scan.port'),
        key: 'port',
        render: (_: unknown, record: ScanHitItem) => displayValue(record.port || record.snapshot?.port),
      },
      {
        title: t('Scan.version'),
        key: 'version',
        render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['version', 'db_version']),
      },
      {
        title: t('Scan.model'),
        dataIndex: 'cmdb_model_id',
        key: 'cmdb_model_id',
        render: (value: string) => value || '--',
      },
      credentialCol,
    ];
  }, [familyTab, t]);

  const networkUnmatchedColumns = [
    { title: t('Scan.host'), dataIndex: 'host', key: 'host', render: renderHost },
    {
      title: t('Scan.sysname'),
      key: 'sysname',
      render: (_: unknown, record: ScanHitItem) => snapshotText(record, ['sysname', 'inst_name']),
    },
    {
      title: t('Scan.soid'),
      key: 'soid',
      render: (_: unknown, record: ScanHitItem) => {
        const val = hitSoid(record);
        return val ? <span className="font-mono text-xs text-[var(--color-text-2)]">{val}</span> : '--';
      },
    },
    {
      title: t('Scan.credential'),
      key: 'credential',
      render: renderCredential,
    },
    {
      title: t('Scan.unmatchReason'),
      key: 'reason',
      render: (_: unknown, record: ScanHitItem) => {
        const isEmpty = record.unmatch_reason === 'empty_soid';
        return (
          <Tag
            className={`!m-0 !rounded !border-0 !px-1.5 !text-xs ${
              isEmpty
                ? '!bg-[var(--color-fill-2)] !text-[var(--color-text-3)]'
                : '!bg-[color-mix(in_srgb,var(--color-warning)_14%,transparent)] !text-[var(--color-warning)]'
            }`}
          >
            {isEmpty ? t('Scan.emptySoid') : t('Scan.unknownSoid')}
          </Tag>
        );
      },
    },
  ];

  const dbUnmatchedColumns = [
    { title: t('Scan.host'), dataIndex: 'host', key: 'host', render: renderHost },
    {
      title: t('Scan.port'),
      key: 'port',
      render: (_: unknown, record: ScanHitItem) => displayValue(record.port || record.snapshot?.port),
    },
    {
      title: t('Scan.model'),
      key: 'model',
      render: (_: unknown, record: ScanHitItem) => (
        <Tag className="!m-0 !rounded !border-0 !bg-[color-mix(in_srgb,var(--color-primary)_10%,transparent)] !px-1.5 !text-xs !text-[var(--color-primary)]">
          {familyLabel(record.family_model_id || '') || record.family_model_id}
        </Tag>
      ),
    },
    {
      title: t('Scan.unmatchReason'),
      key: 'reason',
      render: () => (
        <Tag className="!m-0 !rounded !border-0 !bg-[color-mix(in_srgb,var(--color-warning)_14%,transparent)] !px-1.5 !text-xs !text-[var(--color-warning)]">
          {t('Scan.credentialFailed')}
        </Tag>
      ),
    },
  ];

  const selectedHits = useMemo(
    () => hits.filter((item) => selectedHitIds.includes(item.id)),
    [hits, selectedHitIds]
  );

  const isOnlyDbUnmatchedSelected = useMemo(
    () => selectedHits.length > 0 && selectedHits.every((item) => item.unmatch_reason === 'credential_failed'),
    [selectedHits]
  );

  const actionsDisabled = hitsLoading || !canSplitUnmatched;
  const exportDisabled = hitsLoading || isOnlyDbUnmatchedSelected;
  const targetCount = activeExecution?.target_count ?? 0;
  const receivedCount = activeExecution?.received_count ?? 0;
  const progressPercent = targetCount ? Math.min(100, Math.round((receivedCount / targetCount) * 100)) : 0;

  return (
    <Drawer
      title={
        <div className="flex items-center gap-2">
          <span>{t('Scan.hits')}</span>
          {activeExecution?.id ? (
            <span className="text-xs font-normal text-[var(--color-text-3)]">
              (ID: {activeExecution.id})
            </span>
          ) : null}
        </div>
      }
      open={open}
      width="min(82vw, 1440px)"
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between">
          <div className="text-xs text-[var(--color-text-3)]">
            {selectedHitIds.length > 0 ? (
              <span>
                {t('common.selected')} <strong className="text-[var(--color-primary)]">{selectedHitIds.length}</strong>{' '}
                {t('common.items')}
              </span>
            ) : (
              <span>{t('Scan.selectHitsTip')}</span>
            )}
          </div>
          <Space>
            <PermissionWrapper requiredPermissions={['Execute']} permissionPath={SCAN_PERMISSION_PATH}>
              <Button loading={batchLoading} disabled={exportDisabled} onClick={() => handleBatch('collect')}>
                {t('Scan.generateCollect')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Execute']} permissionPath={SCAN_PERMISSION_PATH}>
              <Button
                type="primary"
                loading={batchLoading}
                disabled={exportDisabled}
                onClick={() => handleBatch('monitor')}
              >
                {t('Scan.pushMonitor')}
              </Button>
            </PermissionWrapper>
          </Space>
        </div>
      }
    >
      <Spin spinning={hitsLoading}>
        {/* 顶部概览指标卡片 */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-2)] p-3.5 shadow-sm">
          {/* 左侧：执行状态与实时进度 */}
          <div className="flex min-w-[280px] flex-1 items-center gap-3">
            <ExecutionStatusBadge
              status={activeExecution?.status}
              label={statusLabel[activeExecution?.status as keyof typeof statusLabel] || activeExecution?.status}
            />
            <div className="flex flex-1 flex-col gap-1 pr-2">
              <div className="flex items-center justify-between text-xs text-[var(--color-text-3)]">
                <span>{t('Scan.progress')}</span>
                <span className="font-mono font-medium text-[var(--color-text-2)]">
                  {receivedCount}/{targetCount} ({progressPercent}%)
                </span>
              </div>
              <Progress
                percent={progressPercent}
                size="small"
                status={
                  activeExecution?.status === 'running' || activeExecution?.status === 'finalizing'
                    ? 'active'
                    : undefined
                }
                strokeColor={activeExecution?.status === 'failed' ? 'var(--color-error)' : 'var(--color-primary)'}
                showInfo={false}
                className="!mb-0"
              />
            </div>
          </div>

          {/* 右侧：关键计数指示 */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3 py-1.5">
              <span className="text-xs text-[var(--color-text-3)]">{t('Scan.hits')}:</span>
              <span className="font-mono text-sm font-semibold text-[var(--color-text-1)]">{hitTotal}</span>
            </div>
            <div className="flex items-center gap-1.5 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-3 py-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-[var(--color-success)]" />
              <span className="text-xs text-[var(--color-text-3)]">{t('Scan.matched')}:</span>
              <span className="font-mono text-sm font-semibold text-[var(--color-success)]">
                {matchedHits.length}
              </span>
            </div>
            {canSplitUnmatched && (
              <div
                className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 ${
                  unmatchedHits.length > 0
                    ? 'border-[color-mix(in_srgb,var(--color-warning)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-warning)_8%,transparent)]'
                    : 'border-[var(--color-border-2)] bg-[var(--color-bg-1)]'
                }`}
              >
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    unmatchedHits.length > 0 ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-text-4)]'
                  }`}
                />
                <span
                  className={`text-xs ${
                    unmatchedHits.length > 0 ? 'font-medium text-[var(--color-warning)]' : 'text-[var(--color-text-3)]'
                  }`}
                >
                  {t('Scan.unmatched')}:
                </span>
                <span
                  className={`font-mono text-sm font-semibold ${
                    unmatchedHits.length > 0 ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-2)]'
                  }`}
                >
                  {unmatchedHits.length}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* 命中详情主 Tab */}
        <Tabs
          activeKey={topTab}
          onChange={(key) => {
            setTopTab(key);
            setMatchedPage(1);
            setNetworkGroupPage(1);
            setDbGroupPage(1);
          }}
          items={[
            {
              key: 'matched',
              label: (
                <span className="flex items-center gap-1.5">
                  {t('Scan.matched')}
                  <Tag className="!m-0 !rounded-full !border-0 !bg-[var(--color-fill-2)] !px-2 !text-xs !text-[var(--color-text-2)]">
                    {matchedHits.length}
                  </Tag>
                </span>
              ),
              children: (
                <div>
                  {!hitsLoading && matchedHits.length === 0 ? (
                    <div className="py-8">
                      <CompactEmptyState description={t('Scan.noHits')} />
                    </div>
                  ) : (
                    <>
                      <Tabs
                        size="small"
                        activeKey={familyTab}
                        onChange={(key) => {
                          setFamilyTab(key);
                          setMatchedPage(1);
                        }}
                        items={matchedFamilies.map((family) => {
                          const count = matchedHits.filter(
                            (hit) => (hit.family_model_id || hit.protocol) === family
                          ).length;
                          return {
                            key: family,
                            label: (
                              <span className="flex items-center gap-1">
                                {familyLabel(family)}
                                <span className="font-mono text-xs text-[var(--color-text-3)]">({count})</span>
                              </span>
                            ),
                          };
                        })}
                      />
                      {/* CustomTable 传入 pagination 时会按父容器高度自撑，抽屉内容会无限增高。 */}
                      <CustomTable
                        rowKey="id"
                        columns={matchedColumns}
                        dataSource={pagedFamilyHits}
                        rowSelection={{
                          selectedRowKeys: selectedHitIds,
                          onChange: (keys) => {
                            const visibleIds = pagedFamilyHits.map((item) => item.id);
                            const kept = selectedHitIds.filter((id) => !visibleIds.includes(id));
                            setSelectedHitIds([...kept, ...(keys as number[])]);
                          },
                        }}
                        pagination={false}
                      />
                      {familyHits.length > TABLE_PAGE_SIZE ? (
                        <div className="flex justify-end p-2.5">
                          <Pagination
                            size="small"
                            current={matchedPage}
                            pageSize={TABLE_PAGE_SIZE}
                            total={familyHits.length}
                            showSizeChanger={false}
                            onChange={(page) => setMatchedPage(page)}
                          />
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              ),
            },
            {
              key: 'unmatched',
              label: (
                <span className="flex items-center gap-1.5">
                  {t('Scan.unmatched')}
                  {unmatchedHits.length > 0 ? (
                    <Tag className="!m-0 !rounded-full !border-0 !bg-[color-mix(in_srgb,var(--color-warning)_18%,transparent)] !px-2 !text-xs !font-medium !text-[var(--color-warning)]">
                      {unmatchedHits.length}
                    </Tag>
                  ) : (
                    <Tag className="!m-0 !rounded-full !border-0 !bg-[var(--color-fill-2)] !px-2 !text-xs !text-[var(--color-text-2)]">
                      0
                    </Tag>
                  )}
                </span>
              ),
              children: (
                <div className="flex flex-col gap-3.5">
                  {!canSplitUnmatched ? (
                    <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-4 text-center text-sm text-[var(--color-text-3)]">
                      {t('Scan.awaitingFinalize')}
                    </div>
                  ) : unmatchedHits.length === 0 ? (
                    <div className="py-8">
                      <CompactEmptyState description={t('Scan.noHits')} />
                    </div>
                  ) : (
                    <>
                      <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-2 text-xs leading-relaxed text-[var(--color-text-3)]">
                        {t('Scan.unmatchedPathTip')}
                      </div>

                      {/* 网络设备未匹配（按 SOID 分组） */}
                      {networkUnmatchedGroups.length > 0 && (
                        <div className="flex flex-col gap-3">
                          {dbUnmatchedGroups.length > 0 && (
                            <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-2)]">
                              <BranchesOutlined />
                              <span>{t('Scan.networkGroup')}</span>
                            </div>
                          )}
                          {pagedNetworkGroups.map((group) => {
                            const ids = group.hits.map((item) => item.id);
                            const allSelected = ids.every((id) => selectedSet.has(id));
                            const someSelected = ids.some((id) => selectedSet.has(id));
                            const hasSoid = group.soid !== EMPTY_SOID_KEY;
                            return (
                              <section
                                key={group.soid}
                                className="overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm transition-all"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-2)] bg-[var(--color-bg-2)] px-4 py-2.5">
                                  <div className="flex items-center gap-3">
                                    <Checkbox
                                      checked={allSelected}
                                      indeterminate={!allSelected && someSelected}
                                      onChange={(event) => toggleRows(ids, event.target.checked)}
                                    />
                                    <div className="flex items-center gap-2">
                                      {hasSoid ? (
                                        <span className="rounded bg-[var(--color-fill-2)] px-2 py-0.5 font-mono text-xs font-semibold text-[var(--color-text-1)]">
                                          SOID: {group.soid}
                                        </span>
                                      ) : (
                                        <span className="rounded bg-[var(--color-fill-2)] px-2 py-0.5 text-xs text-[var(--color-text-3)]">
                                          {t('Scan.emptySoidGroup')}
                                        </span>
                                      )}
                                      <Tag className="!m-0 !rounded-full !border-0 !bg-[var(--color-fill-3)] !px-2 !text-xs !text-[var(--color-text-2)]">
                                        {t('Scan.instanceCount', undefined, { count: group.hits.length })}
                                      </Tag>
                                    </div>
                                  </div>
                                  <Space size="middle">
                                    <Tooltip title={t('Scan.openOidLibrary')}>
                                      <Button
                                        type="link"
                                        size="small"
                                        icon={<ExportOutlined />}
                                        href={oidLibraryUrl(hasSoid ? group.soid : '')}
                                        target="_blank"
                                        className="!px-1 text-xs"
                                      >
                                        {t('Scan.openOidLibrary')}
                                      </Button>
                                    </Tooltip>
                                    <PermissionWrapper
                                      requiredPermissions={['Add']}
                                      permissionPath={SOID_LIBRARY_PATH}
                                    >
                                      <Button
                                        type="primary"
                                        ghost
                                        size="small"
                                        icon={<PlusOutlined />}
                                        disabled={actionsDisabled}
                                        onClick={() => openFingerprint(hasSoid ? group.soid : '', ids)}
                                        className="text-xs"
                                      >
                                        {t('Scan.addFingerprint')}
                                      </Button>
                                    </PermissionWrapper>
                                  </Space>
                                </div>

                                <UnmatchedGroupTable
                                  columns={networkUnmatchedColumns}
                                  hits={group.hits}
                                  selectedHitIds={selectedHitIds}
                                  onSelectedChange={(keys, visibleIds) => {
                                    const kept = selectedHitIds.filter((id) => !visibleIds.includes(id));
                                    setSelectedHitIds([...kept, ...keys]);
                                  }}
                                />
                              </section>
                            );
                          })}

                          {networkUnmatchedGroups.length > GROUP_PAGE_SIZE ? (
                            <div className="flex justify-end pt-1">
                              <Pagination
                                size="small"
                                current={networkGroupPage}
                                pageSize={GROUP_PAGE_SIZE}
                                total={networkUnmatchedGroups.length}
                                showSizeChanger={false}
                                onChange={(page) => setNetworkGroupPage(page)}
                              />
                            </div>
                          ) : null}
                        </div>
                      )}

                      {/* 数据库未匹配（按 family_model_id 分组） */}
                      {dbUnmatchedGroups.length > 0 && (
                        <div className="flex flex-col gap-3">
                          {networkUnmatchedGroups.length > 0 && (
                            <div className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-2)]">
                              <DatabaseOutlined />
                              <span>{t('Scan.databaseGroup')}</span>
                            </div>
                          )}
                          {pagedDbGroups.map((group) => {
                            const ids = group.hits.map((item) => item.id);
                            const allSelected = ids.every((id) => selectedSet.has(id));
                            const someSelected = ids.some((id) => selectedSet.has(id));
                            return (
                              <section
                                key={group.familyModelId}
                                className="overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm transition-all"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-2)] bg-[var(--color-bg-2)] px-4 py-2.5">
                                  <div className="flex items-center gap-3">
                                    <Checkbox
                                      checked={allSelected}
                                      indeterminate={!allSelected && someSelected}
                                      onChange={(event) => toggleRows(ids, event.target.checked)}
                                    />
                                    <div className="flex items-center gap-2">
                                      <span className="rounded bg-[var(--color-fill-2)] px-2 py-0.5 font-medium text-xs text-[var(--color-text-1)]">
                                        {familyLabel(group.familyModelId) || group.familyModelId}
                                      </span>
                                      <Tag className="!m-0 !rounded-full !border-0 !bg-[var(--color-fill-3)] !px-2 !text-xs !text-[var(--color-text-2)]">
                                        {t('Scan.instanceCount', undefined, { count: group.hits.length })}
                                      </Tag>
                                    </div>
                                  </div>
                                  <Space size="middle">
                                    <Tooltip title={t('Scan.openPortLibrary')}>
                                      <Button
                                        type="link"
                                        size="small"
                                        icon={<ExportOutlined />}
                                        href={portLibraryUrl(group.familyModelId)}
                                        target="_blank"
                                        className="!px-1 text-xs"
                                      >
                                        {t('Scan.openPortLibrary')}
                                      </Button>
                                    </Tooltip>
                                    <PermissionWrapper
                                      requiredPermissions={['Add']}
                                      permissionPath={SOID_LIBRARY_PATH}
                                    >
                                      <Button
                                        type="primary"
                                        ghost
                                        size="small"
                                        icon={<PlusOutlined />}
                                        disabled={actionsDisabled}
                                        onClick={() => openPortFingerprint(group.familyModelId)}
                                        className="text-xs"
                                      >
                                        {t('Scan.addFingerprint')}
                                      </Button>
                                    </PermissionWrapper>
                                  </Space>
                                </div>

                                <UnmatchedGroupTable
                                  columns={dbUnmatchedColumns}
                                  hits={group.hits}
                                  selectedHitIds={selectedHitIds}
                                  onSelectedChange={(keys, visibleIds) => {
                                    const kept = selectedHitIds.filter((id) => !visibleIds.includes(id));
                                    setSelectedHitIds([...kept, ...keys]);
                                  }}
                                />
                              </section>
                            );
                          })}

                          {dbUnmatchedGroups.length > GROUP_PAGE_SIZE ? (
                            <div className="flex justify-end pt-1">
                              <Pagination
                                size="small"
                                current={dbGroupPage}
                                pageSize={GROUP_PAGE_SIZE}
                                total={dbUnmatchedGroups.length}
                                showSizeChanger={false}
                                onChange={(page) => setDbGroupPage(page)}
                              />
                            </div>
                          ) : null}
                        </div>
                      )}
                    </>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Spin>

      {/* 录入 SOID 指纹弹窗 */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <PlusOutlined className="text-[var(--color-primary)]" />
            <span>{t('Scan.fingerprintTitle')}</span>
          </div>
        }
        open={fingerprintOpen}
        confirmLoading={fingerprintSaving}
        onCancel={() => setFingerprintOpen(false)}
        onOk={confirmFingerprint}
        destroyOnClose
      >
        <Form form={fingerprintForm} layout="vertical" className="pt-2">
          {!fingerprintOidLocked ? (
            <p className="mb-3 text-xs leading-relaxed text-[var(--color-text-3)]">
              {t('Scan.fingerprintEmptyTip')}
            </p>
          ) : null}
          <Form.Item
            label="sysObjectID"
            name="oid"
            rules={[{ required: true, message: t('required') }]}
          >
            <Input
              disabled={fingerprintOidLocked}
              className="font-mono"
              placeholder={t('Scan.fingerprintOidPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            label={t('OidLibrary.deviceType')}
            name="device_type"
            rules={[{ required: true, message: t('required') }]}
          >
            <div className="grid grid-cols-2 gap-2.5">
              {deviceTypeList.map((option) => {
                const isSelected = selectedFingerprintType === option.key;
                return (
                  <button
                    type="button"
                    key={option.key}
                    onClick={() => fingerprintForm.setFieldsValue({ device_type: option.key })}
                    className={`relative flex items-center gap-2.5 rounded-lg border p-2.5 text-left transition-all ${
                      isSelected
                        ? 'border-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_8%,transparent)] font-medium text-[var(--color-primary)]'
                        : 'border-[var(--color-border-2)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)]'
                    }`}
                  >
                    <div className={isSelected ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}>
                      {DEVICE_TYPE_ICONS[option.key] || <BranchesOutlined className="text-xl" />}
                    </div>
                    <span className="text-sm">{option.label}</span>
                    {isSelected ? (
                      <CheckCircleFilled className="absolute right-2 top-2 text-xs text-[var(--color-primary)]" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </Form.Item>
          <Form.Item
            label={t('OidLibrary.brand')}
            name="brand"
            rules={[{ required: true, message: t('required') }]}
          >
            <Input placeholder={t('common.inputMsg')} />
          </Form.Item>
          <Form.Item
            label={t('OidLibrary.model')}
            name="model"
            rules={[{ required: true, message: t('required') }]}
          >
            <Input placeholder={t('common.inputMsg')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 录入端口指纹弹窗 */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <PlusOutlined className="text-[var(--color-primary)]" />
            <span>{t('Scan.portFingerprintTitle')}</span>
          </div>
        }
        open={portFingerprintOpen}
        confirmLoading={portFingerprintSaving}
        onCancel={() => setPortFingerprintOpen(false)}
        onOk={confirmPortFingerprint}
        destroyOnClose
      >
        <Form form={portFingerprintForm} layout="vertical" className="pt-2">
          <Form.Item label={t('OidLibrary.targetType')} name="target_type">
            <Input disabled value={familyLabel(portFingerprintType) || portFingerprintType} />
          </Form.Item>
          <Form.Item
            label={t('OidLibrary.port')}
            name="port"
            rules={[
              { required: true, message: t('OidLibrary.portPlaceholder') },
              {
                validator: async (_, value) => {
                  if (value === undefined || value === null || value === '') return;
                  const num = Number(value);
                  if (!Number.isInteger(num) || num < 1 || num > 65535) {
                    throw new Error(t('OidLibrary.portPlaceholder'));
                  }
                },
              },
            ]}
          >
            <InputNumber
              min={1}
              max={65535}
              precision={0}
              placeholder="1-65535"
              className="w-full font-mono"
              autoFocus
            />
          </Form.Item>
          <Form.Item label={t('OidLibrary.protocol')} name="protocol" initialValue="tcp">
            <Input disabled value="TCP" className="font-mono uppercase" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 快捷选类型弹窗（网络未匹配） */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <BranchesOutlined className="text-[var(--color-primary)]" />
            <span>{t('Scan.classifyType')}</span>
          </div>
        }
        open={classifyOpen}
        confirmLoading={batchLoading}
        onCancel={() => setClassifyOpen(false)}
        onOk={confirmClassify}
        destroyOnClose
      >
        <p className="mb-4 text-xs text-[var(--color-text-3)] leading-relaxed">
          {t('Scan.classifyTypeTip')}
        </p>
        <Form form={classifyForm} layout="vertical">
          <Form.Item
            name="cmdb_model_id"
            rules={[{ required: true, message: t('required') }]}
            className="!mb-2"
          >
            <div className="grid grid-cols-2 gap-3">
              {deviceTypeList.map((option) => {
                const isSelected = selectedModelId === option.key;
                return (
                  <button
                    type="button"
                    key={option.key}
                    onClick={() => classifyForm.setFieldsValue({ cmdb_model_id: option.key })}
                    className={`relative flex items-center gap-3 rounded-lg border p-3 text-left transition-all ${
                      isSelected
                        ? 'border-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_8%,transparent)] font-medium text-[var(--color-primary)] shadow-sm'
                        : 'border-[var(--color-border-2)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)]'
                    }`}
                  >
                    <div className={isSelected ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}>
                      {DEVICE_TYPE_ICONS[option.key] || <BranchesOutlined className="text-xl" />}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{option.label}</span>
                      <span className="text-[11px] text-[var(--color-text-4)] uppercase">{option.key}</span>
                    </div>
                    {isSelected ? (
                      <CheckCircleFilled className="absolute right-2.5 top-2.5 text-sm text-[var(--color-primary)]" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
};

export default ScanHitsDrawer;
