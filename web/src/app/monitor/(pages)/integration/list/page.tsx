'use client';
import React, { useEffect, useState, useRef } from 'react';
import {
  Spin,
  Input,
  Button,
  Tag,
  message,
  Modal,
  Pagination as AntPagination
} from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconByObjectName, getPluginBrandIcon } from '@/app/monitor/utils/common';
import { useRouter } from 'next/navigation';
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
import { isDerivativeObject } from '@/app/monitor/utils/monitorObject';
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

const { confirm } = Modal;

const Integration = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject, getMonitorPlugin } = useMonitorApi();
  const {
    updateMonitorObject,
    createCustomTemplate,
    updateCustomTemplate,
    deleteCustomTemplate
  } = useIntegrationApi();
  const { t } = useTranslation();
  const router = useRouter();
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
  }, [isLoading, objectId, objectType, pagination.current, pagination.pageSize]);

  useEffect(() => {
    return () => {
      cancelAllRequests();
    };
  }, []);

  const handleNodeDrag = async (data: TreeSortData[]) => {
    try {
      setTreeLoading(true);
      await updateMonitorObject(data);
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
      const data = await getMonitorPlugin(
        {
          ...(monitorObjectId ? { monitor_object_id: monitorObjectId } : {}),
          ...(monitorObjectType
            ? { monitor_object_type: monitorObjectType }
            : {}),
          keyword: params.keyword !== undefined ? params.keyword : searchText,
          page,
          page_size: pagination.pageSize
        },
        {
          signal: abortController.signal
        }
      );
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
            children: []
          });
        }
        return acc;
      },
      {} as Record<string, TreeItem>
    );
    return [
      {
        title: t('common.all'),
        key: 'all',
        children: []
      },
      ...Object.values(groupedData)
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
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${selectedApp.display_name}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
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
    <div className="w-full flex overflow-hidden">
      <ResizableSidebar collapseStorageKey="monitor.integration.list.sidebarCollapsed">
        <div className="h-[calc(100vh-146px)] pt-5 px-2.5 pb-2.5 bg-[var(--color-bg-1)] overflow-y-auto">
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
      <div className="flex-1 min-w-0 bg-[var(--color-bg-1)] p-5">
        <div className="mb-[20px] flex items-start justify-between gap-[16px]">
          <div className="flex flex-1 items-start">
            <Input
              className="w-[400px]"
              placeholder={t('common.searchPlaceHolder')}
              value={searchText}
              allowClear
              onChange={onSearchTxtChange}
              onPressEnter={onTxtPressEnter}
              onClear={onTxtClear}
            />
            <div className="hidden">
              <Button
                className="mx-[8px]"
                type="primary"
                onClick={openImportModal}
              >
                {t('common.import')}
              </Button>
              <Button
                disabled={exportDisabled}
                loading={exportLoading}
                onClick={exportMetric}
              >
                {t('common.export')}
              </Button>
            </div>
          </div>
          <Permission requiredPermissions={['Setting']}>
            <Button type="primary" onClick={() => openCreateTemplateModal()}>
              {t('monitor.integrations.createTemplate')}
            </Button>
          </Permission>
        </div>
        <Spin spinning={pageLoading}>
          {!pluginList.length && !pageLoading ? (
            <CompactEmptyState description={t('common.noData')} />
          ) : !pluginList.length ? (
            <div className="h-[calc(100vh-280px)]" />
          ) : (
            <>
              <div
                className="grid gap-4 w-full h-[calc(100vh-280px)] overflow-y-auto"
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

                  return (
                    <div
                      key={app.id}
                      className="p-2"
                      onClick={() => onAppClick(app)}
                    >
                      <div className="bg-[var(--color-bg-1)] shadow-sm hover:shadow-md transition-shadow duration-300 ease-in-out rounded-lg p-4 relative cursor-pointer group border">
                        <div className="flex items-center space-x-4 my-2">
                          <div className="w-14 h-14 min-w-[56px] rounded-lg flex items-center justify-center bg-[var(--color-fill-1)]">
                            <img
                              src={`/assets/icons/${getPluginBrandIcon(app.name) || getIconByObjectName(objectName, objects)}.svg`}
                              alt={objectName}
                              className="w-12 h-12"
                              onError={(e) => {
                                (e.target as HTMLImageElement).src =
                                  '/assets/icons/cc-default_默认.svg';
                              }}
                            />
                          </div>
                          <div
                            style={{
                              width: 'calc(100% - 60px)'
                            }}
                          >
                            <h2
                              title={app.display_name}
                              className="text-xl font-bold m-0 hide-text"
                            >
                              {app.display_name || '--'}
                            </h2>
                            <Tag className="mt-[4px]">
                              {parentObject?.display_name ||
                                app.parent_monitor_object_display_name ||
                                app.collect_type ||
                                '--'}
                            </Tag>
                            {app.is_custom && (
                              <Tag className="mt-[4px] ml-[6px]">
                                {t('monitor.integrations.selfBuilt')}
                              </Tag>
                            )}
                          </div>
                        </div>
                        <p
                          className="mb-[15px] text-[var(--color-text-3)] text-[13px] h-[54px] overflow-hidden line-clamp-3"
                          title={app.display_description || '--'}
                        >
                          {app.display_description || '--'}
                        </p>
                        {app.is_custom && (
                          <div
                            className="absolute top-[12px] right-[12px]"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreActionsDropdown
                              items={buildTemplateActionItems(app)}
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
              <div className="mt-4 flex justify-end">
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
            </>
          )}
        </Spin>
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
