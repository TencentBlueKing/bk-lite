'use client';
import React, { useEffect, useState, useRef } from 'react';
import {
  Spin,
  Input,
  Button,
  Tag,
  message,
  Empty,
  Dropdown,
  Menu,
  Modal
} from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import { EllipsisOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { getIconByObjectName } from '@/app/monitor/utils/common';
import { useRouter } from 'next/navigation';
import {
  ModalRef,
  TableDataItem,
  TreeItem,
  TreeSortData,
  ObjectItem
} from '@/app/monitor/types';
import ImportModal from './importModal';
import axios from 'axios';
import { useAuth } from '@/context/auth';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { useSearchParams } from 'next/navigation';
import Permission from '@/components/permission';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { isDerivativeObject } from '@/app/monitor/utils/monitorObject';
import { cloneDeep } from 'lodash';
import CreateTemplateModal from './createTemplateModal';

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

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (isLoading || !objects?.length) return;
    getPluginList({ monitor_object_id: objectId });
  }, [objectId, isLoading, objects]);

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
      getObjects();
    } catch {
      setTreeLoading(false);
    }
  };

  const cancelAllRequests = () => {
    pluginAbortControllerRef.current?.abort();
  };

  const handleObjectChange = async (id: string) => {
    cancelAllRequests();
    setObjectId(id === 'all' ? '' : id);
  };

  const getPluginList = async (params = {}) => {
    pluginAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    pluginAbortControllerRef.current = abortController;
    const currentRequestId = ++pluginRequestIdRef.current;
    setPluginList([]);
    setSelectedApp(null);
    setExportDisabled(true);
    setPageLoading(true);
    try {
      const data = await getMonitorPlugin(params, {
        signal: abortController.signal
      });
      if (currentRequestId !== pluginRequestIdRef.current) return;
      // 根据objects的顺序对插件列表进行排序
      const sortedData = data.sort((a: ObjectItem, b: ObjectItem) => {
        const indexA = objects.findIndex(
          (obj) => obj.id === a.parent_monitor_object
        );
        const indexB = objects.findIndex(
          (obj) => obj.id === b.parent_monitor_object
        );
        // 如果找不到对应的object,放在最后
        if (indexA === -1) return 1;
        if (indexB === -1) return -1;
        return indexA - indexB;
      });
      setPluginList(sortedData);
    } finally {
      if (currentRequestId === pluginRequestIdRef.current) {
        setPageLoading(false);
      }
    }
  };

  const getObjects = async () => {
    try {
      setTreeLoading(true);
      const data: ObjectItem[] = await getMonitorObject();
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
            key: item.id,
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
        url: `/api/proxy/monitor/api/monitor_plugin/export/${selectedApp.id}/`, // 替换为你的导出数据的API端点
        method: 'GET',
        responseType: 'blob', // 确保响应类型为blob
        headers: {
          Authorization: `Bearer ${tokenRef.current}`
        }
      });
      const text = await response.data.text();
      const json = JSON.parse(text);
      // 将data对象转换为JSON字符串并创建Blob对象
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
    const params = {
      monitor_object_id: objectId === 'all' ? '' : objectId,
      name: searchText
    };
    getPluginList(params);
  };

  const onTxtClear = () => {
    setSearchText('');
    getPluginList({
      monitor_object_id: objectId === 'all' ? '' : objectId,
      name: ''
    });
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
    onTxtClear();
  };

  const handleDeleteTemplate = async (id: number) => {
    await deleteCustomTemplate(id);
    message.success(t('common.deleteSuccess'));
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
    const parentObject: any = objects.find(
      (item) => item.id === app.parent_monitor_object
    );
    const objectInfo = parentObject || {};
    if (objectInfo.id) {
      objectInfo.icon = objectInfo.icon || OBJECT_DEFAULT_ICON;
    }
    const row: TableDataItem = {
      id: objectInfo.id || '',
      icon: objectInfo.icon || OBJECT_DEFAULT_ICON,
      name: objectInfo.name || '',
      plugin_name: app?.name,
      plugin_id: app?.id,
      template_type: app?.template_type,
      plugin_display_name: app?.display_name,
      plugin_description: app?.display_description || '--'
    };
    const params = new URLSearchParams(row);
    const targetUrl = `/monitor/integration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  };

  const onAppClick = (app: ObjectItem) => {
    setSelectedApp(app);
    setExportDisabled(false); // Enable the export button
  };

  const renderTemplateActionMenu = (app: ObjectItem) => (
    <Menu onClick={(e) => e.domEvent.stopPropagation()}>
      <Menu.Item className="!p-0" onClick={() => openCreateTemplateModal(app)}>
        <Button type="text" className="w-full !justify-start">
          {t('common.edit')}
        </Button>
      </Menu.Item>
      <Menu.Item
        className="!p-0"
        onClick={() => handleDeleteTemplateConfirm(app.id as number)}
      >
        <Button type="text" className="w-full !justify-start">
          {t('common.delete')}
        </Button>
      </Menu.Item>
    </Menu>
  );

  return (
    <div className="w-full flex overflow-hidden">
      <div className="h-[calc(100vh-146px)] pt-5 px-2.5 pb-2.5 bg-[var(--color-bg-1)] w-[210px] min-w-[210px] mr-2.5 overflow-y-auto">
        <TreeSelector
          showAllMenu
          data={treeData}
          defaultSelectedKey={
            searchParams.get('objId')
              ? Number(searchParams.get('objId'))
              : 'all'
          }
          loading={treeLoading}
          draggable
          onNodeSelect={handleObjectChange}
          onNodeDrag={handleNodeDrag}
        />
      </div>
      <div className="w-full bg-[var(--color-bg-1)] p-5">
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
          {!pluginList.length ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div
              className="grid gap-4 w-full h-[calc(100vh-236px)] overflow-y-auto"
              style={{
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                alignContent: 'start'
              }}
            >
              {pluginList.map((app) => {
                const parentObject: any = objects.find(
                  (item) => item.id === app.parent_monitor_object
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
                            src={`/app/assets/assetModelIcon/${getIconByObjectName(objectName, objects)}.svg`}
                            alt={objectName}
                            className="w-12 h-12"
                            onError={(e) => {
                              (e.target as HTMLImageElement).src =
                                '/app/assets/assetModelIcon/cc-default_默认.svg';
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
                            {app.collect_type || '--'}
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
                          <Dropdown
                            dropdownRender={() => renderTemplateActionMenu(app)}
                            placement="bottomRight"
                            trigger={['click']}
                          >
                            <Button type="text" icon={<EllipsisOutlined />} />
                          </Dropdown>
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
