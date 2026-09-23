'use client';
import './register-asset-pilot';
import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import {
  Input,
  Button,
  message,
  Dropdown,
  Space,
  Tooltip,
  Modal,
  Switch,
  Tag
} from 'antd';
import CatalogScopeSegmented from '@/components/catalog-scope-segmented';
import useApiClient from '@/utils/request';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import useViewApi from '@/app/monitor/api/view';
import { findByMonitorId, sameMonitorId, toMonitorIdString } from '@/app/monitor/utils/monitorIds';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import { resolveMonitorObjectQueryId } from '@/app/monitor/utils/monitorObjectQuery';
import { comparePackVersions } from '@/app/monitor/utils/collectNeedUpdate';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  TreeItem,
  ModalRef,
  Organization,
  Pagination,
  TableDataItem,
  ObjectItem
} from '@/app/monitor/types';
import {
  ObjectInstItem,
  TemplateDrawerRef
} from '@/app/monitor/types/integration';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { DownOutlined, PlusOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/monitor/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import { useAssetMenuItems } from '@/app/monitor/hooks/integration/common/assetMenuItems';
import {
  showGroupName,
  getBaseInstanceColumn
} from '@/app/monitor/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import TreeSelector from '@/app/monitor/components/treeSelector';
import EditConfig from './updateConfig';
import EditInstance from './editInstance';
import TemplateConfigDrawer from './templateConfigDrawer';
import { isDerivativeObject } from '@/app/monitor/utils/monitorObject';
import CompactEmptyState from '@/components/compact-empty-state';
import Permission from '@/components/permission';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { TableProps, MenuProps } from 'antd';
import type { FilterValue } from 'antd/es/table/interface';
import { cloneDeep } from 'lodash';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import { resolveDashboardUrl } from '@/app/monitor/dashboards/registry';
import { buildAssetViewUrl } from './viewRoute';
import PluginTooltipContent, { PluginTooltipTrigger } from './pluginTooltip';
import { getAssetSearchPlaceholderKey } from '@/app/monitor/utils/assetSearchPlaceholder';

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];

const ASSET_IP_FACT = 'asset.ip';
const ASSET_IP_COLUMN_KEY = `summary_fact:${ASSET_IP_FACT}`;

const sameStringArray = (left: string[], right: string[]) =>
  left.length === right.length && left.every((item) => right.includes(item));

const normalizeIpList = (values: unknown): string[] => {
  if (!Array.isArray(values)) return [];
  return Array.from(
    new Set(
      values
        .map((item) => String(item ?? '').trim())
        .filter(Boolean)
    )
  );
};

const Asset = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const {
    deleteMonitorInstance,
    getInstanceListByPrimaryObject,
    updateCollectTemplateConfigs
  } = useIntegrationApi();
  const { getInstanceQueryParams } = useViewApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchparams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { syncObjectId } = useMonitorObjectQuery();
  const urlObjId = resolveMonitorObjectQueryId({
    searchParams: searchparams,
    fallback: ''
  });
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const configRef = useRef<ModalRef>(null);
  const assetAbortControllerRef = useRef<AbortController | null>(null);
  const assetRequestIdRef = useRef<number>(0);
  const instanceRef = useRef<ModalRef>(null);
  const templateDrawerRef = useRef<TemplateDrawerRef>(null);
  const assetMenuItems = useAssetMenuItems();
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const { isSuperUser } = useUserInfoContext();
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [unassignedCount, setUnassignedCount] = useState<number | undefined>(undefined);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>(
    urlObjId ? toMonitorIdString(urlObjId) : ''
  );
  const [objectId, setObjectId] = useState<React.Key>('');
  const [frequence, setFrequence] = useState<number>(0);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [ipFilterOptions, setIpFilterOptions] = useState<string[]>([]);
  const [selectedAssetIps, setSelectedAssetIps] = useState<string[]>([]);
  const selectedAssetIpsRef = useRef<string[]>([]);
  const [needUpdateOnly, setNeedUpdateOnly] = useState(
    searchparams.get('need_update') === '1'
  );
  const [stalePluginId, setStalePluginId] = useState(
    searchparams.get('monitor_plugin_id') || ''
  );
  const [updatingKeys, setUpdatingKeys] = useState<React.Key[]>([]);
  const [modal, modalContextHolder] = Modal.useModal();

  useEffect(() => {
    selectedAssetIpsRef.current = selectedAssetIps;
  }, [selectedAssetIps]);

  useEffect(() => {
    const nextNeedUpdate = searchparams.get('need_update') === '1';
    const nextPluginId = searchparams.get('monitor_plugin_id') || '';
    setNeedUpdateOnly((prev) => (prev === nextNeedUpdate ? prev : nextNeedUpdate));
    setStalePluginId((prev) => (prev === nextPluginId ? prev : nextPluginId));
  }, [searchparams]);

  const needsAssetIpFilter = useMemo(() => {
    const target = findByMonitorId(objects, objectId);
    return (target?.instance_summary_columns || []).some(
      (column) => column.fact === ASSET_IP_FACT
    );
  }, [objects, objectId]);

  const handleAssetMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'batchDelete') {
      showBatchDeleteConfirm();
      return;
    }
    if (e.key === 'batchUpdateCollectConfig') {
      batchUpdateCollectConfigs();
      return;
    }
    openInstanceModal(
      {
        keys: selectedRowKeys
      },
      e.key
    );
  };

  const assetMenuProps = {
    items: assetMenuItems,
    onClick: handleAssetMenuClick
  };

  const openTemplateDrawer = (
    record: any,
    options?: { selectedConfigId?: string; showTemplateList?: boolean }
  ) => {
    templateDrawerRef.current?.showModal({
      instanceName: record.instance_name,
      instanceId: record.instance_id,
      selectedConfigId: options?.selectedConfigId,
      objName: findByMonitorId(objects, objectId)?.name || '',
      monitorObjId: objectId,
      plugins: record.plugins || [],
      showTemplateList: options?.showTemplateList ?? true
    });
  };

  const getPluginLatestVersion = (plugin?: {
    pack_version?: string;
    latest_pack_version?: string;
  }) =>
    String(plugin?.latest_pack_version || plugin?.pack_version || '').trim();

  const getPluginAppliedVersionText = (plugin?: {
    applied_pack_version?: string;
    pack_version?: string;
    latest_pack_version?: string;
    need_update?: boolean;
  }) => {
    const applied = String(plugin?.applied_pack_version || '').trim();
    if (applied) return applied;
    if (plugin?.need_update) {
      return t('monitor.integrations.unknownAppliedPack');
    }
    return (
      getPluginLatestVersion(plugin) || t('monitor.integrations.builtinPack')
    );
  };

  const getNeedUpdateHint = (
    version: string,
    direction: 'upgrade' | 'downgrade' | 'align' = 'upgrade'
  ) => {
    const hintKey =
      direction === 'downgrade'
        ? 'monitor.integrations.needUpdateHintDowngrade'
        : direction === 'align'
          ? 'monitor.integrations.needUpdateHintAlign'
          : 'monitor.integrations.needUpdateHint';
    return t(hintKey, '', { version });
  };

  const getNeedUpdateTagText = (
    version: string,
    direction: 'upgrade' | 'downgrade' | 'align'
  ) => {
    const tagKey =
      direction === 'downgrade'
        ? 'monitor.integrations.needUpdateToVersionDowngrade'
        : direction === 'align'
          ? 'monitor.integrations.needUpdateToVersionAlign'
          : 'monitor.integrations.needUpdateToVersion';
    return t(tagKey, '', { version });
  };

  const getTargetVersionLabel = (direction: 'upgrade' | 'downgrade' | 'align') => {
    if (direction === 'downgrade') {
      return t('monitor.integrations.updateCollectConfigConfirmTargetVersionDowngrade');
    }
    if (direction === 'align') {
      return t('monitor.integrations.updateCollectConfigConfirmTargetVersionAlign');
    }
    return t('monitor.integrations.updateCollectConfigConfirmTargetVersion');
  };

  const columns = useMemo(() => {
    const columnItems: ColumnItem[] = [
      {
        title: t('monitor.integrations.collectionTemplate'),
        dataIndex: 'plugins',
        key: 'plugins',
        onCell: () => ({
          style: {
            overflow: 'hidden'
          }
        }),
        render: (_, record: any) => {
          const plugins = record.plugins || [];
          if (!plugins.length) return <>--</>;

          return (
            <div className="flex max-w-full flex-wrap items-center gap-1">
              {plugins.map((plugin: any) => {
                const isAuto = plugin.collect_mode === 'auto';
                const statusInfo = {
                  color: ['normal', 'online'].includes(plugin.status)
                    ? 'success'
                    : 'error',
                  text: isAuto
                    ? t('monitor.integrations.automatic')
                    : t('monitor.integrations.manual')
                };

                const statusText =
                  plugin.status === 'normal' || plugin.status === 'online'
                    ? t('monitor.integrations.normal')
                    : t('monitor.integrations.unavailable');
                const timeText = plugin.time
                  ? convertToLocalizedTime(plugin.time)
                  : '--';
                const packVersionText = getPluginAppliedVersionText(plugin);
                const upgradeTargetVersion =
                  getPluginLatestVersion(plugin) ||
                  t('monitor.integrations.builtinPack');
                const updateDirection = comparePackVersions(
                  packVersionText ===
                    t('monitor.integrations.unknownAppliedPack')
                    ? ''
                    : packVersionText,
                  getPluginLatestVersion(plugin)
                );
                const needUpdateHint = getNeedUpdateHint(
                  upgradeTargetVersion,
                  updateDirection
                );
                const tooltipTitle = (
                  <PluginTooltipContent
                    statusText={statusText}
                    lastReportTimeLabel={t(
                      'monitor.integrations.lastReportTime'
                    )}
                    timeText={timeText}
                    collectionNodeLabel={t(
                      'monitor.integrations.collectionNode'
                    )}
                    notAssociatedText={t(
                      'monitor.integrations.notAssociated'
                    )}
                    packVersionLabel={t('monitor.integrations.packVersion')}
                    packVersionText={packVersionText}
                    collectMode={plugin.collect_mode}
                    collectorNodes={plugin.collector_nodes}
                  />
                );

                return (
                  <React.Fragment key={plugin.name}>
                    <style>{`
                      .asset-tooltip.ant-tooltip {
                        max-width: none;
                      }
                    `}</style>
                    <span className="inline-flex max-w-full flex-wrap items-center gap-1">
                      <PluginTooltipTrigger
                        ariaLabel={`${plugin.display_name || '--'}，${statusText}`}
                        color={statusInfo.color}
                        onActivate={() =>
                          openTemplateDrawer(record, {
                            selectedConfigId: isAuto ? plugin.name : undefined,
                            showTemplateList: false
                          })
                        }
                        title={tooltipTitle}
                      >
                        {plugin.display_name || '--'}
                      </PluginTooltipTrigger>
                      {plugin.need_update ? (
                        <Tooltip title={needUpdateHint}>
                          <Tag className="m-0" color="warning">
                            {getNeedUpdateTagText(
                              upgradeTargetVersion,
                              updateDirection
                            )}
                          </Tag>
                        </Tooltip>
                      ) : null}
                    </span>
                  </React.Fragment>
                );
              })}
            </div>
          );
        }
      },
      {
        title: t('monitor.group'),
        dataIndex: 'organization',
        key: 'organization',
        onCell: () => ({
          style: {
            minWidth: 120
          }
        }),
        render: (_, { organization }) => (
          <EllipsisWithTooltip
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            text={
              organization?.length
                ? showGroupName(organization, organizationList)
                : t('common.unassigned')
            }
          />
        )
      },
      {
        title: t('monitor.views.externalId'),
        dataIndex: 'external_id',
        key: 'external_id',
        width: 80,
        ellipsis: true,
        onHeaderCell: () => ({
          style: { width: 80, minWidth: 80, maxWidth: 80 },
        }),
        onCell: () => ({
          style: {
            width: 80,
            minWidth: 80,
            maxWidth: 80,
            overflow: 'hidden',
          },
        }),
        render: (_, record: TableDataItem) => {
          const cmdbId = record.cmdb_id ? String(record.cmdb_id) : '--';
          const nodeId = record.node_id ? String(record.node_id) : '--';
          return (
            <Tooltip
              title={
                <div className="text-xs leading-5">
                  <div>
                    {t('monitor.views.cmdbId')}: {cmdbId}
                  </div>
                  <div>
                    {t('monitor.views.nodeId')}: {nodeId}
                  </div>
                </div>
              }
            >
              <div
                className="block overflow-hidden cursor-default"
                style={{ width: 64, maxWidth: 64 }}
              >
                <div className="overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12px] leading-[18px]">
                  {cmdbId}
                </div>
                <div className="overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12px] leading-[18px] text-[var(--color-text-3)]">
                  {nodeId}
                </div>
              </div>
            </Tooltip>
          );
        },
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 280,
        fixed: 'right',
        render: (_, record) => {
          const canOperate = Array.isArray(record.permission)
            ? record.permission.includes('Operate')
            : false;
          const moreItems: MoreActionsDropdownItem[] = [];
          if (canOperate && record.need_update && !record.can_update) {
            moreItems.push({
              key: 'goToEdit',
              label: t('monitor.integrations.goToEditConfig'),
              permission: 'Edit',
              onClick: () => openHandEditedConfig(record)
            });
          }
          if (canOperate) {
            moreItems.push({
              key: 'remove',
              label: t('common.remove'),
              permission: 'Delete',
              danger: true,
              confirm: {
                title: t('common.deleteTitle'),
                content: t('common.deleteContent')
              },
              onClick: () => deleteInstConfirm(record)
            });
          }
          return (
            <>
              <Button
                type="link"
                onClick={() => checkDetail(record as ObjectInstItem)}
              >
                {t('monitor.view')}
              </Button>
              <Permission
                requiredPermissions={['Edit']}
                instPermissions={record.permission}
              >
                <Button
                  type="link"
                  className="ml-[10px]"
                  onClick={() => openInstanceModal(record, 'edit')}
                >
                  {t('common.edit')}
                </Button>
              </Permission>
              <Permission
                requiredPermissions={['Edit']}
                instPermissions={record.permission}
              >
                <Button
                  type="link"
                  className="ml-[10px]"
                  onClick={() =>
                    openTemplateDrawer(record, { showTemplateList: true })
                  }
                >
                  {t('monitor.integrations.configure')}
                </Button>
              </Permission>
              {record.can_update ? (
                <Permission
                  requiredPermissions={['Edit']}
                  instPermissions={record.permission}
                >
                  <Button
                    type="link"
                    className="ml-[10px]"
                    loading={updatingKeys.includes(record.instance_id)}
                    onClick={() =>
                      confirmUpgradeCollectConfigs(
                        [record.instance_id],
                        record
                      )
                    }
                  >
                    {t('monitor.integrations.updateCollectConfig')}
                  </Button>
                </Permission>
              ) : null}
              {record.need_update && !record.can_update ? (
                <Permission
                  requiredPermissions={['Edit']}
                  instPermissions={record.permission}
                >
                  <Button
                    type="link"
                    className="ml-[10px]"
                    loading={updatingKeys.includes(record.instance_id)}
                    onClick={() =>
                      confirmDiscardHandEditedCollectConfigs(record)
                    }
                  >
                    {t('monitor.integrations.discardHandEditedAndUpgrade')}
                  </Button>
                </Permission>
              ) : null}
              {moreItems.length ? (
                <MoreActionsDropdown
                  items={moreItems}
                  buttonType="link"
                  buttonSize="middle"
                  placement="bottomRight"
                />
              ) : null}
            </>
          );
        }
      }
    ];
    const row = findByMonitorId(objects, objectId) || {};
    const mergedIpOptions = Array.from(
      new Set(
        [
          ...ipFilterOptions,
          ...selectedAssetIps,
          ...tableData.flatMap((item) => {
            const facts = item?.summary_facts as
              | Record<string, unknown>
              | undefined;
            const factIp = facts?.[ASSET_IP_FACT];
            const fallbackIp = item?.ip;
            return [factIp, fallbackIp]
              .filter((value) => value != null && value !== '')
              .map((value) => String(value).trim());
          })
        ].filter(Boolean)
      )
    ).sort((left, right) =>
      left.localeCompare(right, undefined, { numeric: true })
    );
    const assetIpFilters = mergedIpOptions.map((ip) => ({
      text: ip,
      value: ip
    }));
    return [
      ...getBaseInstanceColumn({
        objects,
        row: row as ObjectItem,
        t,
        ipFilterOptions: mergedIpOptions
      }),
      ...columnItems
    ].map((column) => {
      let withWidth = column;
      if (!column.width && column.key !== 'action') {
        const key = String(column.key);
        let width = 150;
        if (key === ASSET_IP_COLUMN_KEY) width = 160;
        else if (column.key === 'plugins') width = 320;
        else if (column.key === 'organization') width = 140;
        else if (column.key === 'instance_name') width = 180;
        withWidth = { ...column, width };
      }
      if (String(withWidth.key) !== ASSET_IP_COLUMN_KEY) return withWidth;
      return {
        ...withWidth,
        filterMultiple: true,
        filterSearch: true,
        filterParam: ASSET_IP_FACT,
        filters: assetIpFilters.length ? assetIpFilters : undefined,
        filteredValue: selectedAssetIps.length ? selectedAssetIps : null
      };
    });
  }, [
    objects,
    objectId,
    t,
    convertToLocalizedTime,
    ipFilterOptions,
    selectedAssetIps,
    tableData,
    organizationList,
    updatingKeys
  ]);

  const enableOperateAsset = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys]);

  useEffect(() => {
    if (!isLoading) {
      getObjects();
    }
  }, [isLoading]);

  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const fetchUnassignedCount = useCallback(async (currentObjId: React.Key) => {
    if (!isSuperUser || !currentObjId) {
      setUnassignedCount(0);
      return;
    }
    try {
      const data = await getInstanceListByPrimaryObject({
        id: String(currentObjId),
        page: 1,
        page_size: 1,
        unassigned: true,
      });
      setUnassignedCount(data?.count || 0);
    } catch {
      setUnassignedCount(0);
    }
  }, [isSuperUser, getInstanceListByPrimaryObject]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
      void fetchUnassignedCount(objectId);
    } else {
      setUnassignedCount(0);
    }
  }, [objectId, fetchUnassignedCount, isSuperUser]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [pagination.current, pagination.pageSize, unassignedOnly]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [needUpdateOnly, stalePluginId]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [selectedAssetIps]);

  // 与监控视图一致：有 asset.ip 摘要列时拉取去重候选 IP。
  useEffect(() => {
    if (!objectId || !needsAssetIpFilter) {
      setIpFilterOptions([]);
      return;
    }
    const objName = findByMonitorId(objects, objectId)?.name;
    if (!objName) return;
    let cancelled = false;
    getInstanceQueryParams(objName, { monitor_object_id: objectId })
      .then((data) => {
        if (cancelled) return;
        setIpFilterOptions(
          normalizeIpList(
            Array.isArray(data?.asset_ips) ? data.asset_ips : []
          ).sort((left, right) =>
            left.localeCompare(right, undefined, { numeric: true })
          )
        );
      })
      .catch(() => {
        if (!cancelled) setIpFilterOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [objectId, needsAssetIpFilter, objects, getInstanceQueryParams]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getObjects('timer');
      getAssetInsts(objectId, 'timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    objectId,
    pagination.current,
    pagination.pageSize,
    searchText,
    unassignedOnly,
    needUpdateOnly,
    stalePluginId
  ]);

  const onRefresh = () => {
    getObjects();
    getAssetInsts(objectId);
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const cancelAllRequests = () => {
    assetAbortControllerRef.current?.abort();
  };

  const handleObjectChange = (id: string) => {
    cancelAllRequests();
    setTableData([]);
    setSelectedRowKeys([]);
    setSelectedAssetIps([]);
    selectedAssetIpsRef.current = [];
    setIpFilterOptions([]);
    setStalePluginId('');
    setObjectId(id);
    syncObjectId(id);
  };

  const openInstanceModal = (row = {}, type: string) => {
    instanceRef.current?.showModal({
      title: t(`common.${type}`),
      type,
      form: row
    });
  };

  const checkDetail = (row: ObjectInstItem) => {
    const monitorItem = objects.find(
      (item: ObjectItem) => sameMonitorId(item.id, objectId)
    );
    const url = buildAssetViewUrl({
      objectId: objectId || '',
      monitorItem,
      row,
      resolveProfessionalDashboardUrl: (objectName, objectDisplayName, queryString) =>
        resolveDashboardUrl({
          monitorObjectName: objectName,
          monitorObjectDisplayName: objectDisplayName,
          instancePlugins: Array.isArray(row.plugins) ? row.plugins : undefined,
          queryString,
        }),
    });
    router.push(url);
  };

  const handleTableChange = (
    paginationConfig: any,
    filters?: Record<string, FilterValue | null>
  ) => {
    if (filters && ASSET_IP_COLUMN_KEY in filters) {
      const next = normalizeIpList(filters[ASSET_IP_COLUMN_KEY]);
      if (!sameStringArray(next, selectedAssetIps)) {
        setSelectedAssetIps(next);
        selectedAssetIpsRef.current = next;
        setTableData([]);
        setPagination((prev: Pagination) => ({
          ...prev,
          current: 1
        }));
        return;
      }
    }
    setPagination(paginationConfig);
  };

  const getAssetInsts = async (objectId: React.Key, type?: string) => {
    assetAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    assetAbortControllerRef.current = abortController;
    const currentRequestId = ++assetRequestIdRef.current;
    try {
      setTableLoading(type !== 'timer');
      const selectedIps = selectedAssetIpsRef.current;
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
        name: type === 'clear' ? '' : searchText,
        id: String(objectId),
        ...(unassignedOnly ? { unassigned: true } : {}),
        ...(selectedIps.length
          ? { vm_params: { [ASSET_IP_FACT]: selectedIps.join(',') } }
          : {}),
        ...(needUpdateOnly
          ? {
            need_update: true,
            ...(stalePluginId
              ? { monitor_plugin_id: stalePluginId }
              : {})
          }
          : {})
      };
      const data = await getInstanceListByPrimaryObject(params, {
        signal: abortController.signal
      });
      if (currentRequestId !== assetRequestIdRef.current) return;
      setTableData(data?.results || []);
      const totalCount = data?.count || 0;
      setPagination((prev: Pagination) => ({
        ...prev,
        total: totalCount
      }));
      if (unassignedOnly) {
        setUnassignedCount(totalCount);
      }
    } finally {
      if (currentRequestId === assetRequestIdRef.current) {
        setTableLoading(false);
      }
    }
  };

  const getObjects = async (type?: string) => {
    try {
      setTreeLoading(type !== 'timer');
      const params = {
        name: '',
        add_instance_count: true
      };
      const data = await getMonitorObject(params);
      setObjects(data);
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
      const defaultKey = resolveMonitorObjectQueryId({
        searchParams: searchparams,
        objects: data,
        fallback: defaultSelectObj || data[0]?.id
      });
      if (defaultKey) {
        setDefaultSelectObj(toMonitorIdString(defaultKey));
      }
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce(
      (acc, item) => {
        if (!acc[item.type]) {
          acc[item.type] = {
            title: item.display_type || '--',
            key: item.type,
            children: []
          };
        }
        if (!isDerivativeObject(item, data)) {
          acc[item.type].children.push({
            title: item.display_name || '--',
            label: item.name || '--',
            key: toMonitorIdString(item.id),
            icon: item.icon,
            count: item.instance_count ?? 0,
            children: []
          });
        }
        return acc;
      },
      {} as Record<string, TreeItem>
    );
    return Object.values(groupedData);
  };

  const deleteInstConfirm = async (row: any) => {
    const data = {
      instance_ids: [row.instance_id],
      clean_child_config: true
    };
    await deleteMonitorInstance(data);
    message.success(t('common.successfullyDeleted'));
    setSelectedRowKeys((keys) =>
      keys.filter((key) => key !== row.instance_id)
    );
    await refreshAfterDeletionSafely(1);
  };

  const refreshAfterDeletion = async (deletedCount: number) => {
    const remainingTotal = Math.max(0, pagination.total - deletedCount);
    const lastPage = Math.max(1, Math.ceil(remainingTotal / pagination.pageSize));
    const targetPage = Math.min(pagination.current, lastPage);

    setPagination((prev) => ({
      ...prev,
      current: targetPage,
      total: remainingTotal
    }));

    if (targetPage === pagination.current) {
      await Promise.all([getObjects(), getAssetInsts(objectId)]);
      return;
    }
    await getObjects();
  };

  const refreshAfterDeletionSafely = async (deletedCount: number) => {
    try {
      await refreshAfterDeletion(deletedCount);
    } catch {
      message.warning(
        `${t('common.successfullyDeleted')} ${t('common.fetchFailed')}`
      );
    }
  };

  const batchDeleteInstConfirm = async () => {
    const instanceIds = [...selectedRowKeys];
    const data = {
      instance_ids: instanceIds,
      clean_child_config: true
    };
    await deleteMonitorInstance(data);
    setSelectedRowKeys([]);
    message.success(t('common.successfullyDeleted'));
    await refreshAfterDeletionSafely(instanceIds.length);
  };

  const showBatchDeleteConfirm = () => {
    const selectedCount = selectedRowKeys.length;
    if (!selectedCount) return;

    modal.confirm({
      title: t('common.batchDelete'),
      content: `${t('common.selected')} ${selectedCount} ${t(
        'common.items'
      )} · ${t('common.deleteContent')}`,
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: batchDeleteInstConfirm
    });
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts(objectId, 'clear');
  };

  const openHandEditedConfig = (record: any) => {
    const plugins = record.plugins || [];
    const target =
      plugins.find((plugin: any) => plugin.need_update && plugin.hand_edited) ||
      plugins.find((plugin: any) => plugin.need_update);
    openTemplateDrawer(record, {
      selectedConfigId: target?.name,
      showTemplateList: !target
    });
  };

  const reportCollectUpdateResult = (result: {
    updated?: string[];
    skipped?: Array<{ reason?: string }>;
    failed?: unknown[];
    truncated?: boolean;
    max_instances?: number;
  }) => {
    const updated = result?.updated?.length || 0;
    const skippedItems = result?.skipped || [];
    const skipped = skippedItems.length;
    const unauthorized = skippedItems.filter(
      (item) => item?.reason === 'unauthorized'
    ).length;
    const handEdited = skippedItems.filter(
      (item) => item?.reason === 'hand_edited'
    ).length;
    const failed = result?.failed?.length || 0;
    if (result?.truncated) {
      message.warning(
        t('monitor.integrations.updateCollectConfigTruncated', '', {
          max: result.max_instances || 200
        })
      );
    }
    if (failed || skipped) {
      message.warning(
        t('monitor.integrations.updateCollectConfigPartial', '', {
          updated,
          skipped: handEdited,
          unauthorized,
          failed
        })
      );
      return;
    }
    message.success(t('monitor.integrations.updateCollectConfigSuccess'));
  };

  const updateCollectConfigs = async (
    instanceIds: React.Key[],
    options?: { discardHandEdited?: boolean; pluginId?: React.Key }
  ) => {
    // 过滤指定插件时只升该插件；否则不传 plugin_id，与确认框列出的全部可升级探针一致。
    const pluginId = options?.pluginId || stalePluginId || undefined;
    setUpdatingKeys(instanceIds);
    try {
      const result = await updateCollectTemplateConfigs({
        instance_ids: instanceIds,
        ...(pluginId ? { monitor_plugin_id: pluginId } : {}),
        ...(options?.discardHandEdited ? { discard_hand_edited: true } : {})
      });
      reportCollectUpdateResult(result || {});
      // 保持「可升级」过滤，刷新后剩余 stale 仍可见。
      await getAssetInsts(objectId);
    } finally {
      setUpdatingKeys([]);
    }
  };

  const confirmUpgradeCollectConfigs = (
    instanceIds: React.Key[],
    record?: any
  ) => {
    const rows = record
      ? [record]
      : tableData.filter((item) =>
        instanceIds.includes(item.instance_id as React.Key)
      );
    const upgradeItems = rows.flatMap((item) =>
      (item.plugins || [])
        .filter((plugin: any) => {
          if (!plugin?.can_update) return false;
          if (stalePluginId) {
            return String(plugin.plugin_id) === String(stalePluginId);
          }
          return true;
        })
        .map((plugin: any) => {
          const currentVersion = getPluginAppliedVersionText(plugin);
          const targetVersion =
            getPluginLatestVersion(plugin) ||
            t('monitor.integrations.builtinPack');
          const direction = comparePackVersions(
            currentVersion === t('monitor.integrations.unknownAppliedPack')
              ? ''
              : currentVersion,
            getPluginLatestVersion(plugin)
          );
          return {
            instanceName: item.instance_name || item.instance_id || '--',
            probeName:
              plugin.display_name ||
              plugin.name ||
              plugin.collector ||
              '--',
            currentVersion,
            targetVersion,
            direction
          };
        })
    );
    if (!upgradeItems.length) {
      message.warning(t('monitor.integrations.noUpdatableCollectConfig'));
      return;
    }
    const hasMixedDirection = upgradeItems.some(
      (item) => item.direction !== upgradeItems[0].direction
    );

    modal.confirm({
      title: t('monitor.integrations.updateCollectConfigConfirmTitle'),
      width: 480,
      content: (
        <div className="max-h-[280px] space-y-3 overflow-y-auto">
          {upgradeItems.map((item, index) => {
            const targetLabel = hasMixedDirection
              ? getTargetVersionLabel(item.direction)
              : getTargetVersionLabel(upgradeItems[0]?.direction || 'upgrade');
            return (
              <div
                key={`${item.instanceName}-${item.probeName}-${index}`}
                className="rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2 text-sm leading-6"
              >
                {upgradeItems.length > 1 ? (
                  <div className="mb-1 text-[var(--color-text-2)]">
                    {item.instanceName}
                    {item.probeName ? ` · ${item.probeName}` : ''}
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[var(--color-text-3)]">
                    {t(
                      'monitor.integrations.updateCollectConfigConfirmCurrentVersion'
                    )}
                  </span>
                  <span className="text-[var(--color-text-1)]">
                    {item.currentVersion}
                  </span>
                  <span className="text-[var(--color-text-3)]">→</span>
                  <span className="text-[var(--color-text-3)]">
                    {targetLabel}
                  </span>
                  <Tag className="m-0" color="warning">
                    {item.targetVersion}
                  </Tag>
                </div>
              </div>
            );
          })}
        </div>
      ),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: () => updateCollectConfigs(instanceIds)
    });
  };

  const confirmDiscardHandEditedCollectConfigs = (record: any) => {
    const discardPlugins = (record.plugins || []).filter((plugin: any) => {
      if (!plugin?.need_update || plugin?.can_update) return false;
      if (stalePluginId) {
        return String(plugin.plugin_id) === String(stalePluginId);
      }
      return true;
    });
    if (!discardPlugins.length) {
      message.warning(t('monitor.integrations.noUpdatableCollectConfig'));
      return;
    }
    const pluginId =
      discardPlugins.length === 1 ? discardPlugins[0].plugin_id : stalePluginId;
    modal.confirm({
      title: t('monitor.integrations.discardHandEditedConfirmTitle'),
      width: 480,
      content: (
        <div className="space-y-3">
          <div className="text-[var(--color-text-2)] leading-6">
            {t('monitor.integrations.discardHandEditedConfirmTip')}
          </div>
          <div className="max-h-[280px] space-y-3 overflow-y-auto">
            {discardPlugins.map((plugin: any) => (
              <div
                key={plugin.plugin_id || plugin.name}
                className="rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2"
              >
                {[
                  {
                    label: t('monitor.integrations.instanceName'),
                    value: record.instance_name || record.instance_id || '--'
                  },
                  {
                    label: t(
                      'monitor.integrations.updateCollectConfigConfirmProbeName'
                    ),
                    value:
                      plugin.display_name ||
                      plugin.name ||
                      plugin.collector ||
                      '--'
                  },
                  {
                    label: t(
                      'monitor.integrations.updateCollectConfigConfirmCurrentVersion'
                    ),
                    value: getPluginAppliedVersionText(plugin)
                  },
                  {
                    label: t(
                      'monitor.integrations.updateCollectConfigConfirmTargetVersionAlign'
                    ),
                    value:
                      getPluginLatestVersion(plugin) ||
                      t('monitor.integrations.builtinPack')
                  }
                ].map((row) => (
                  <div
                    key={row.label}
                    className="flex gap-3 py-1 text-sm leading-5"
                  >
                    <span className="w-[108px] shrink-0 text-[var(--color-text-3)]">
                      {row.label}
                    </span>
                    <span className="min-w-0 break-all text-[var(--color-text-1)]">
                      {row.value}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: () =>
        updateCollectConfigs([record.instance_id], {
          discardHandEdited: true,
          pluginId
        })
    });
  };

  const batchUpdateCollectConfigs = async () => {
    const rows = tableData.filter((item) =>
      selectedRowKeys.includes(item.instance_id as React.Key)
    );
    const updatable = rows.filter((item) => item.can_update);
    if (!updatable.length) {
      message.warning(t('monitor.integrations.noUpdatableCollectConfig'));
      return;
    }
    confirmUpgradeCollectConfigs(
      updatable.map((item) => item.instance_id as React.Key)
    );
  };

  const syncNeedUpdateQuery = (checked: boolean) => {
    const params = new URLSearchParams(searchparams.toString());
    if (checked) {
      params.set('need_update', '1');
    } else {
      params.delete('need_update');
      params.delete('monitor_plugin_id');
      setStalePluginId('');
    }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const setNeedUpdateFilter = (checked: boolean) => {
    setNeedUpdateOnly(checked);
    setPagination((prev) => ({ ...prev, current: 1 }));
    syncNeedUpdateQuery(checked);
  };

  // 跳转到集成列表页面进行接入
  const goToIntegration = () => {
    const targetUrl = `/monitor/integration/list?objId=${String(objectId)}`;
    router.push(targetUrl);
  };

  //判断是否禁用按钮
  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const rowSelection: TableRowSelection<TableDataItem> = {
    selectedRowKeys,
    onChange: onSelectChange,
    getCheckboxProps: (record: any) => {
      return {
        disabled: Array.isArray(record.permission)
          ? !record.permission.includes('Operate')
          : false
      };
    }
  };

  const handleCatalogScopeChange = (checked: boolean) => {
    setUnassignedOnly(checked);
    setSelectedRowKeys([]);
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  return (
    <>
      {modalContextHolder}
      <div className={assetStyle.asset}>
        <ResizableSidebar collapseStorageKey="monitor.integration.asset.sidebarCollapsed">
          <div className={assetStyle.tree}>
            <TreeSelector
              data={treeData}
              defaultSelectedKey={defaultSelectObj as string}
              onNodeSelect={handleObjectChange}
              loading={treeLoading}
            />
          </div>
        </ResizableSidebar>
        <div className={assetStyle.table}>
          <div className={assetStyle.search}>
            <Input
              allowClear
              placeholder={t(getAssetSearchPlaceholderKey(findByMonitorId(objects, objectId)))}
              className="w-full max-w-[420px] min-w-0"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onPressEnter={() => getAssetInsts(objectId)}
              onClear={clearText}
            />
            <div className="flex shrink-0 items-center gap-3">
              <label className="inline-flex h-8 items-center gap-1.5 text-[var(--color-text-2)]">
                <Switch
                  size="small"
                  checked={needUpdateOnly}
                  onChange={setNeedUpdateFilter}
                />
                {t('monitor.integrations.needUpdateFilter')}
              </label>
              <div className="flex items-center gap-2">
                <CatalogScopeSegmented
                  unassignedOnly={unassignedOnly}
                  onChange={handleCatalogScopeChange}
                  count={unassignedCount}
                  resourceName={t('common.instance', '监控实例')}
                />
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={goToIntegration}
                >
                  {t('monitor.integrations.access')}
                </Button>
                <Dropdown
                  overlayClassName="customMenu"
                  menu={assetMenuProps}
                  disabled={enableOperateAsset}
                >
                  <Button>
                    <Space>
                      {t('common.action')}
                      <DownOutlined />
                    </Space>
                  </Button>
                </Dropdown>
                <TimeSelector
                  onlyRefresh
                  className="[&>div]:!ml-0"
                  onFrequenceChange={onFrequenceChange}
                  onRefresh={onRefresh}
                />
              </div>
            </div>
          </div>
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable
              key={String(objectId || 'asset-table')}
              scroll={{ x: 'max-content' }}
              columns={columns}
              dataSource={tableData}
              pagination={pagination}
              loading={tableLoading}
              rowKey="instance_id"
              onChange={handleTableChange}
              rowSelection={rowSelection}
              locale={{
                emptyText: needUpdateOnly ? (
                  <CompactEmptyState
                    description={t('monitor.integrations.needUpdateEmpty')}
                  >
                    <Button
                      type="link"
                      onClick={() => setNeedUpdateFilter(false)}
                    >
                      {t('monitor.integrations.needUpdateEmptyAction')}
                    </Button>
                  </CompactEmptyState>
                ) : undefined
              }}
            />
          </div>
        </div>
      </div>
      <EditConfig
        ref={configRef}
        onSuccess={() => {
          getAssetInsts(objectId);
          if (objectId) void fetchUnassignedCount(objectId);
        }}
      />
      <EditInstance
        ref={instanceRef}
        organizationList={organizationList}
        onSuccess={() => {
          getAssetInsts(objectId);
          if (objectId) void fetchUnassignedCount(objectId);
        }}
      />
      <TemplateConfigDrawer
        ref={templateDrawerRef}
        onSuccess={() => getAssetInsts(objectId)}
      />
    </>
  );
};

export default Asset;
