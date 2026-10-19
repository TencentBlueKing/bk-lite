'use client';
import './register-list-pilot';
import React, { useEffect, useState, useRef } from 'react';
import {
  Button,
  Tooltip,
  message,
  Modal,
  Pagination as AntPagination
} from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import SearchActionBar from '@/components/search-action-bar';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import SourceOriginBadge from '@/components/source-origin-badge';
import { StatusToneBadge } from '@/app/monitor/utils/statusTone';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconByObjectName, getPluginBrandIcon } from '@/app/monitor/utils/common';
import { useScreenAwareRouter } from '@/console-layout';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import {
  isMonitorObjectTypeQueryKey,
  resolveMonitorObjectQueryId
} from '@/app/monitor/utils/monitorObjectQuery';
import {
  ModalRef,
  TreeItem,
  TreeSortData,
  ObjectItem,
  Pagination
} from '@/app/monitor/types';
import ImportModal from './importModal';
import axios from 'axios';
import { useAuth } from '@/context/auth';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { useSearchParams } from 'next/navigation';
import Permission from '@/components/permission';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import {
  buildMonitorObjectSidebarTree,
  collectCloudFamilyPlatformIds,
  isCloudFamilySidebarType,
  resolveCloudFamilyTypeQueryValues,
  UNIFIED_CLOUD_ROOT_TYPE,
  uniqueMonitorRecords
} from '@/app/monitor/utils/monitorObject';
import { sameMonitorId, toMonitorIdString } from '@/app/monitor/utils/monitorIds';
import { cloneDeep } from 'lodash';
import CreateTemplateModal from './createTemplateModal';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import {
  invalidateMonitorObjectsCache,
  loadMonitorObjectsCached
} from '@/app/monitor/utils/monitorObjectCache';
import { unwrapMonitorPluginList } from '@/app/monitor/utils/monitorPluginList';
import { invalidateMonitorPluginCache } from '@/app/monitor/utils/monitorPluginCache';
import {
  buildIntegrationConfigureUrl,
  resolveIntegrationEntryContext
} from '@/app/monitor/utils/integrationEntryContext';
import { buildCollectNeedUpdateAssetUrl } from '@/app/monitor/utils/collectNeedUpdate';
import { resolvePluginSourceBadge } from '@/app/monitor/utils/pluginSourceBadge';
import { downloadPluginConfig } from './exportDownload';

const { confirm } = Modal;

const expandCloudFamilySortData = (
  sortData: TreeSortData[],
  objectItems: ObjectItem[]
): TreeSortData[] => {
  const byName = new Map(objectItems.map((item) => [item.name, item]));
  const expanded: TreeSortData[] = [];
  for (const item of sortData) {
    if (item.type === 'all') {
      continue;
    }
    if (!isCloudFamilySidebarType(item.type)) {
      expanded.push(item);
      continue;
    }
    const lists = new Map<string, string[]>();
    for (const name of item.object_list || []) {
      const originalType = byName.get(name)?.type || UNIFIED_CLOUD_ROOT_TYPE;
      const list = lists.get(originalType) || [];
      list.push(name);
      lists.set(originalType, list);
    }
    if (!lists.size) {
      expanded.push({ type: UNIFIED_CLOUD_ROOT_TYPE, object_list: [] });
      continue;
    }
    for (const [type, object_list] of lists) {
      expanded.push({ type, object_list });
    }
  }
  return expanded;
};

const Integration = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject, getMonitorPlugin } = useMonitorApi();
  const {
    updateMonitorObject,
    createCustomTemplate,
    updateCustomTemplate,
    deleteCustomTemplate,
    restoreBuiltinPlugin
  } = useIntegrationApi();
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const importRef = useRef<ModalRef>(null);
  const createTemplateRef = useRef<ModalRef>(null);
  const authContext = useAuth();
  const token = authContext?.token || null;
  const tokenRef = useRef(token);
  const pluginAbortControllerRef = useRef<AbortController | null>(null);
  const pluginRequestIdRef = useRef<number>(0);
  const searchParams = useSearchParams();
  const { syncObjectId } = useMonitorObjectQuery();
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [exportDisabled, setExportDisabled] = useState<boolean>(true);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [selectedApp, setSelectedApp] = useState<ObjectItem | null>(null);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [pluginList, setPluginList] = useState<ObjectItem[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [objectId, setObjectId] = useState<React.Key>('');
  const [objectType, setObjectType] = useState<string>('');
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20
  });

  // objects 与 plugins 并行:plugins 不再等 objects 就绪
  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (isLoading) return;
    getPluginList();
  }, [
    isLoading,
    objectId,
    objectType,
    objects,
    pagination.current,
    pagination.pageSize
  ]);

  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const handleNodeDrag = async (data: TreeSortData[]) => {
    try {
      setTreeLoading(true);
      await updateMonitorObject(expandCloudFamilySortData(data, objects));
      message.success(t('common.updateSuccess'));
      invalidateMonitorObjectsCache();
      getObjects({ force: true });
    } catch {
      setTreeLoading(false);
    }
  };

  const cancelAllRequests = () => {
    pluginAbortControllerRef.current?.abort();
  };

  const isTypeNodeKey = (key: string) => isMonitorObjectTypeQueryKey(key);

  const handleObjectChange = async (id: string) => {
    const nextObjectType =
      id && id !== 'all' && isTypeNodeKey(String(id)) ? String(id) : '';
    const nextObjectId = !id || id === 'all' || nextObjectType ? '' : id;
    // URL 回写同一节点时不要 abort 刚发出的插件列表请求，否则右侧会停在上一对象。
    if (
      String(objectId) === String(nextObjectId) &&
      String(objectType) === String(nextObjectType)
    ) {
      syncObjectId(id || 'all');
      return;
    }
    cancelAllRequests();
    setPagination((prev) => ({ ...prev, current: 1 }));
    syncObjectId(id || 'all');
    setObjectId(nextObjectId);
    setObjectType(nextObjectType);
  };

  const getPluginList = async (
    params: {
      monitor_object_id?: React.Key | null;
      monitor_object_type?: string | null;
      keyword?: string;
      page?: number;
    } = {}
  ) => {
    pluginAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    pluginAbortControllerRef.current = abortController;
    const currentRequestId = ++pluginRequestIdRef.current;
    const page = params.page ?? pagination.current;
    // 翻页保留旧列表,仅 Spin overlay,避免闪 Empty
    setSelectedApp(null);
    setExportDisabled(true);
    setPageLoading(true);
    try {
      const monitorObjectId =
        params.monitor_object_id !== undefined
          ? params.monitor_object_id
          : objectId;
      const monitorObjectType =
        params.monitor_object_type !== undefined
          ? params.monitor_object_type
          : objectType;
      const keyword =
        params.keyword !== undefined ? params.keyword : searchText;
      const familyPlatformIds =
        !monitorObjectId && isCloudFamilySidebarType(String(monitorObjectType))
          ? collectCloudFamilyPlatformIds(objects)
          : [];
      const familyTypeIds =
        !monitorObjectId &&
        isCloudFamilySidebarType(String(monitorObjectType)) &&
        !familyPlatformIds.length
          ? resolveCloudFamilyTypeQueryValues(String(monitorObjectType))
          : [];
      const fetchPluginPage = (
        query: {
          monitor_object_id?: React.Key | null;
          monitor_object_type?: string | null;
          page?: number;
          page_size?: number;
        }
      ) =>
        getMonitorPlugin(
          {
            ...(query.monitor_object_id
              ? { monitor_object_id: query.monitor_object_id }
              : {}),
            ...(query.monitor_object_type
              ? { monitor_object_type: query.monitor_object_type }
              : {}),
            keyword,
            page: query.page ?? page,
            page_size: query.page_size ?? pagination.pageSize
          },
          {
            signal: abortController.signal
          }
        );
      // 点「云」根：按侧栏 4 个平台对象（或云族 type）并集取卡，避免只命中 type=Cloud 的 SCP/CNware。
      if (familyPlatformIds.length || familyTypeIds.length) {
        const pages = await Promise.all(
          familyPlatformIds.length
            ? familyPlatformIds.map((id) =>
              fetchPluginPage({
                monitor_object_id: id,
                page: 1,
                page_size: -1
              })
            )
            : familyTypeIds.map((typeId) =>
              fetchPluginPage({
                monitor_object_type: typeId,
                page: 1,
                page_size: -1
              })
            )
        );
        if (currentRequestId !== pluginRequestIdRef.current) return;
        const all = uniqueMonitorRecords(
          pages.flatMap((data) => unwrapMonitorPluginList<ObjectItem>(data))
        );
        const start = (page - 1) * pagination.pageSize;
        setPluginList(all.slice(start, start + pagination.pageSize));
        setPagination((prev) => ({
          ...prev,
          current: page,
          total: all.length
        }));
        return;
      }
      const data = await fetchPluginPage({
        monitor_object_id: monitorObjectId,
        monitor_object_type: monitorObjectType
      });
      if (currentRequestId !== pluginRequestIdRef.current) return;
      const items = unwrapMonitorPluginList<ObjectItem>(data);
      const count = Array.isArray(data)
        ? data.length
        : typeof data?.count === 'number'
          ? data.count
          : 0;
      setPluginList(items);
      setPagination((prev) => ({
        ...prev,
        current: page,
        total: count
      }));
    } catch (error: any) {
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        return;
      }
    } finally {
      if (currentRequestId === pluginRequestIdRef.current) {
        setPageLoading(false);
      }
    }
  };

  const getObjects = async (options: { force?: boolean } = {}) => {
    try {
      setTreeLoading(true);
      if (options.force) {
        invalidateMonitorObjectsCache();
      }
      const data = await loadMonitorObjectsCached(() => getMonitorObject());
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
      setObjects(data);
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const tree = buildMonitorObjectSidebarTree(
      data,
      (item) => ({
        title: item.display_name || '--',
        label: item.name || '--',
        key: toMonitorIdString(item.id),
        icon: item.icon,
        children: []
      }),
      { attachCloudDerivatives: false }
    );
    return [
      {
        title: t('common.all'),
        key: 'all',
        children: []
      },
      ...tree
    ];
  };

  const exportMetric = async () => {
    if (!selectedApp) return;
    try {
      setExportLoading(true);
      const response = await axios({
        url: `/api/proxy/monitor/api/monitor_plugin/export/${selectedApp.id}/`,
        method: 'GET',
        responseType: 'blob',
        headers: {
          Authorization: `Bearer ${tokenRef.current}`
        }
      });
      const text = await response.data.text();
      const json = JSON.parse(text);
      const blob = new Blob([JSON.stringify(json.data, null, 2)], {
        type: 'application/json'
      });
      downloadPluginConfig(blob, `${selectedApp.display_name}.json`);
      message.success(t('common.successfullyExported'));
    } catch (error) {
      message.error(error as string);
    } finally {
      setExportLoading(false);
    }
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const onTxtPressEnter = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
    getPluginList({
      monitor_object_id: objectId,
      monitor_object_type: objectType,
      keyword: searchText,
      page: 1
    });
  };

  const onTxtClear = () => {
    setSearchText('');
    setPagination((prev) => ({ ...prev, current: 1 }));
    getPluginList({
      monitor_object_id: objectId,
      monitor_object_type: objectType,
      keyword: '',
      page: 1
    });
  };

  const handlePageChange = (page: number, pageSize: number) => {
    setPagination((prev) => ({
      ...prev,
      current: page,
      pageSize
    }));
  };

  const openImportModal = () => {
    importRef.current?.showModal({
      title: t('common.import'),
      type: 'add',
      form: {}
    });
  };

  const openCreateTemplateModal = (app?: any) => {
    const selectedObject = objects.find(
      (item) => String(item.id) === String(objectId)
    );

    createTemplateRef.current?.showModal({
      title: app ? t('common.edit') : t('common.add'),
      type: app ? 'edit' : 'add',
      form:
        app ||
        (selectedObject ? { parent_monitor_object: selectedObject.id } : {})
    });
  };

  const handleTemplateSubmit = async (
    values: Record<string, any>,
    mode: 'add' | 'edit',
    id?: number
  ) => {
    if (mode === 'edit' && id) {
      await updateCustomTemplate(id, values);
      message.success(t('common.updateSuccess'));
    } else {
      await createCustomTemplate(values);
      message.success(t('common.addSuccess'));
    }
    invalidateMonitorPluginCache(objectId);
    onTxtClear();
  };

  const handleDeleteTemplate = async (id: number) => {
    await deleteCustomTemplate(id);
    message.success(t('common.deleteSuccess'));
    invalidateMonitorPluginCache(objectId);
    onTxtClear();
  };

  const handleDeleteTemplateConfirm = (id: number) => {
    confirm({
      title: t('common.deleteTitle'),
      content: t('common.deleteContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return handleDeleteTemplate(id);
      }
    });
  };

  const linkToDetial = (app: ObjectItem) => {
    const result = resolveIntegrationEntryContext(app, objects);
    if (!result.ok) {
      message.error(t('monitor.integrations.missingEntryContext'));
      return;
    }
    const icon = getPluginBrandIcon(app.name) || result.context.objectIcon;
    router.push(
      buildIntegrationConfigureUrl(
        { ...result.context, objectIcon: icon },
        OBJECT_DEFAULT_ICON
      )
    );
  };

  const onAppClick = (app: ObjectItem) => {
    setSelectedApp(app);
    setExportDisabled(false);
  };

  const handleRestoreBuiltin = (app: ObjectItem) => {
    confirm({
      title: t('monitor.integrations.restoreBuiltin'),
      content: t('monitor.integrations.restoreBuiltinConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return restoreBuiltinPlugin(app.id).then((result: any) => {
          const staleCount = Number(result?.stale_instance_count) || 0;
          invalidateMonitorPluginCache(objectId);
          getPluginList({
            monitor_object_id: objectId,
            monitor_object_type: objectType,
            keyword: searchText,
            page: pagination.current
          });
          if (staleCount > 0) {
            Modal.success({
              title: t('monitor.integrations.restoreBuiltinSuccess'),
              content: t('monitor.integrations.restoreBuiltinStaleHint', '', {
                count: staleCount
              }),
              okText: t('monitor.integrations.goToStaleAssets'),
              onOk: () => {
                router.push(
                  buildCollectNeedUpdateAssetUrl({
                    monitorObjectId:
                      result?.monitor_object_id ||
                      app.parent_monitor_object ||
                      objectId,
                    pluginId: result?.plugin_id || app.id
                  })
                );
              }
            });
            return;
          }
          message.success(t('monitor.integrations.restoreBuiltinSuccess'));
        });
      }
    });
  };

  const buildTemplateActionItems = (app: ObjectItem): MoreActionsDropdownItem[] => [
    {
      key: 'edit',
      label: t('common.edit'),
      onClick: () => openCreateTemplateModal(app),
    },
    {
      key: 'delete',
      label: t('common.delete'),
      danger: true,
      onClick: () => handleDeleteTemplateConfirm(app.id as number),
    },
  ];

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 gap-2.5 overflow-hidden">
      <ResizableSidebar collapseStorageKey="monitor.integration.list.sidebarCollapsed">
        <div className="flex h-full min-h-0 w-full flex-col overflow-y-auto overflow-x-hidden bg-[var(--color-bg-1)] px-2.5 py-5">
          <TreeSelector
            showAllMenu
            allowParentSelect
            data={treeData}
            defaultSelectedKey={resolveMonitorObjectQueryId({
              searchParams,
              objects,
              allowAll: true,
              allowTypeKeys: true,
              fallback: 'all'
            })}
            loading={treeLoading}
            draggable
            onNodeSelect={handleObjectChange}
            onNodeDrag={handleNodeDrag}
          />
        </div>
      </ResizableSidebar>
      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1)] p-5">
        <SearchActionBar
          searchProps={{
            placeholder: t('common.searchPlaceHolder'),
            value: searchText,
            allowClear: true,
            onChange: onSearchTxtChange,
            onSearch: onTxtPressEnter,
            onClear: onTxtClear,
          }}
          searchClassName="w-80"
          actions={(
            <Permission requiredPermissions={['Setting']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreateTemplateModal()}>
                {t('common.new')}
              </Button>
            </Permission>
          )}
        />
        <div className="hidden">
          <Button className="mx-[8px]" type="primary" onClick={openImportModal}>
            {t('common.import')}
          </Button>
          <Button disabled={exportDisabled} loading={exportLoading} onClick={exportMetric}>
            {t('common.export')}
          </Button>
        </div>
        {pageLoading && !pluginList.length ? (
          <CardGridSkeleton className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4" />
        ) : !pluginList.length ? (
          <CompactEmptyState description={t('common.noData')} />
        ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              <div
                className="grid min-h-0 w-full flex-1 gap-4 overflow-y-auto"
                style={{
                  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                  alignContent: 'start'
                }}
              >
                {pluginList.map((app) => {
                  const parentObject: any = objects.find(
                    (item) => sameMonitorId(item.id, app.parent_monitor_object)
                  );
                  const objectName = parentObject?.name || '';
                  const staleCount = Number(app.stale_instance_count) || 0;
                  const sourceBadge = resolvePluginSourceBadge(app);
                  const packVersionText =
                    sourceBadge.packKind === 'pinned'
                      ? sourceBadge.packVersion
                      : t('monitor.integrations.builtinPack');

                  return (
                    <div
                      key={app.id}
                      className="p-2"
                      onClick={() => onAppClick(app)}
                    >
                      <div className="relative cursor-pointer rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.03)] transition-shadow duration-300 ease-in-out hover:shadow-md group">
                        <div className="my-2 flex items-center gap-3">
                          <div className="grid h-10 w-10 min-w-10 shrink-0 place-items-center rounded-md bg-[var(--color-fill-1)]">
                            <img
                              src={`/assets/icons/${getPluginBrandIcon(app.name) || getIconByObjectName(objectName, objects)}.svg`}
                              alt={objectName}
                              className="h-7 w-7"
                              onError={(e) => {
                                (e.target as HTMLImageElement).src =
                                  '/assets/icons/cc-default_默认.svg';
                              }}
                            />
                          </div>
                          <div className="min-w-0 flex-1">
                            <h2
                              title={app.display_name}
                              className="m-0 truncate text-base font-semibold text-[var(--color-text-1)]"
                            >
                              {app.display_name || '--'}
                            </h2>
                            <div className="mt-1 flex flex-wrap items-center gap-1.5">
                              <span className="text-xs text-[var(--color-text-3)]">
                                {parentObject?.display_name ||
                                  app.parent_monitor_object_display_name ||
                                  app.collect_type ||
                                  '--'}
                              </span>
                              {sourceBadge.showPackTag && (
                                <Tooltip
                                  title={
                                    staleCount > 0
                                      ? t('monitor.integrations.staleInstanceHint', '', {
                                        count: staleCount,
                                        version: packVersionText
                                      })
                                      : sourceBadge.packKind === 'pinned'
                                        ? t('monitor.integrations.pinnedPackHint', '', {
                                          version: sourceBadge.packVersion
                                        })
                                        : t('monitor.integrations.builtinPackHint')
                                  }
                                >
                                  <button
                                    type="button"
                                    className={staleCount > 0 ? 'cursor-pointer' : 'cursor-default'}
                                    onClick={
                                      staleCount > 0
                                        ? (e) => {
                                          e.stopPropagation();
                                          const result =
                                            resolveIntegrationEntryContext(
                                              app,
                                              objects
                                            );
                                          router.push(
                                            buildCollectNeedUpdateAssetUrl({
                                              monitorObjectId: result.ok
                                                ? result.context.objectId
                                                : app.parent_monitor_object ||
                                                  String(objectId),
                                              pluginId: app.id,
                                              needUpdate: true
                                            })
                                          );
                                        }
                                        : undefined
                                    }
                                  >
                                    <SourceOriginBadge
                                      kind={sourceBadge.packKind === 'pinned' ? 'imported' : 'builtin'}
                                      label={packVersionText}
                                    />
                                  </button>
                                </Tooltip>
                              )}
                              {staleCount > 0 && (
                                <Tooltip
                                  title={t('monitor.integrations.staleInstanceHint', '', {
                                    count: staleCount,
                                    version: packVersionText
                                  })}
                                >
                                  <button
                                    type="button"
                                    className="cursor-pointer"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      const result = resolveIntegrationEntryContext(
                                        app,
                                        objects
                                      );
                                      router.push(
                                        buildCollectNeedUpdateAssetUrl({
                                          monitorObjectId: result.ok
                                            ? result.context.objectId
                                            : app.parent_monitor_object ||
                                              String(objectId),
                                          pluginId: app.id,
                                          needUpdate: true
                                        })
                                      );
                                    }}
                                  >
                                    <StatusToneBadge
                                      tone="warning"
                                      label={`${t('monitor.integrations.needUpdate')} ${staleCount}`}
                                    />
                                  </button>
                                </Tooltip>
                              )}
                              {sourceBadge.showSelfBuilt && (
                                <SourceOriginBadge
                                  kind="custom"
                                  label={t('monitor.integrations.selfBuilt')}
                                />
                              )}
                            </div>
                          </div>
                        </div>
                        <p
                          className="mb-[15px] text-[var(--color-text-3)] text-[13px] h-[54px] overflow-hidden line-clamp-3"
                          title={app.display_description || '--'}
                        >
                          {app.display_description || '--'}
                        </p>
                        {(app.is_custom || app.pack_version) && (
                          <div
                            className="absolute top-[12px] right-[12px]"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreActionsDropdown
                              items={[
                                ...(app.pack_version
                                  ? [
                                    {
                                      key: 'restore',
                                      label: t(
                                        'monitor.integrations.restoreBuiltin'
                                      ),
                                      onClick: () => handleRestoreBuiltin(app)
                                    }
                                  ]
                                  : []),
                                ...(app.is_custom
                                  ? buildTemplateActionItems(app)
                                  : [])
                              ]}
                              placement="bottomRight"
                              stopPropagation
                            />
                          </div>
                        )}
                        <div className="w-full h-[32px] flex justify-center items-end">
                          <Permission
                            requiredPermissions={['Setting']}
                            className="w-full"
                          >
                            <Button
                              icon={<PlusOutlined />}
                              type="primary"
                              className="w-full rounded-md transition-opacity duration-300"
                              onClick={(e) => {
                                e.stopPropagation();
                                linkToDetial(app);
                              }}
                            >
                              {t('monitor.integrations.access')}
                            </Button>
                          </Permission>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex shrink-0 justify-end">
                <AntPagination
                  current={pagination.current}
                  pageSize={pagination.pageSize}
                  total={pagination.total}
                  showSizeChanger
                  showTotal={(total) =>
                    `${t('common.total')} ${total} ${t('common.items')}`
                  }
                  onChange={handlePageChange}
                />
              </div>
            </div>
        )}
      </div>
      <ImportModal ref={importRef} onSuccess={onTxtClear} />
      <CreateTemplateModal
        ref={createTemplateRef}
        objects={objects}
        onSubmit={handleTemplateSubmit}
      />
    </div>
  );
};

export default Integration;
