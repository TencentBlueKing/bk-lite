'use client';

import React, {
  useState,
  useMemo,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import Icon from '@/components/icon';
import GroupTreeSelect from '@/components/group-tree-select';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import useBtnPermissions from '@/hooks/usePermissions';
import type { DataNode } from 'antd/lib/tree';
import {
  Button,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Spin,
  Tree,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useDirectoryApi } from '@/app/ops-analysis/api/index';
import { useUserInfoContext } from '@/context/userInfo';
import { ExportModal, ImportModal } from './importExport';
import { ObjectType } from '@/app/ops-analysis/api/importExport';
import { buildDefaultScreenViewSets } from '@/app/ops-analysis/(pages)/view/screen/utils/viewport';
import {
  useNetworkTopologyApi,
} from '@/app/ops-analysis/api/networkTopology';
import {
  CANVAS_TYPES,
  getCanvasTypeMeta,
  isCanvasType,
  type CanvasType,
} from '@/app/ops-analysis/constants/canvasTypes';
import {
  SidebarProps,
  SidebarRef,
  DirItem,
  ModalAction,
  DirectoryType,
  FormValues,
  ItemData,
} from '@/app/ops-analysis/types';
import {
  PlusOutlined,
  BarChartOutlined,
  FolderOutlined,
  ApartmentOutlined,
  DesktopOutlined,
  FileTextOutlined,
  CheckOutlined,
  BranchesOutlined,
} from '@ant-design/icons';
import { resolveSidebarTreeSelection } from '@/app/ops-analysis/utils/sidebarSelection';

const Sidebar = forwardRef<SidebarRef, SidebarProps>(
  ({ onSelect, onDataUpdate }, ref) => {
    const [form] = Form.useForm();
    const selectedCanvasType = Form.useWatch('canvasType', form) as
      | CanvasType
      | undefined;
    const { t } = useTranslation();
    const searchParams = useSearchParams();
    const { selectedGroup } = useUserInfoContext();
    const { hasPermission } = useBtnPermissions();
    const networkTopologyApi = useNetworkTopologyApi();
    const [dirs, setDirs] = useState<DirItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [submitLoading, setSubmitLoading] = useState(false);
    const [connectionTesting, setConnectionTesting] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [modalVisible, setModalVisible] = useState(false);
    const [modalTitle, setModalTitle] = useState('');
    const [modalAction, setModalAction] = useState<ModalAction>('addRoot');
    const [newItemType, setNewItemType] = useState<DirectoryType>('directory');
    const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
    const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
    const { getDirectoryTree, createItem, updateItem, deleteItem } =
      useDirectoryApi();
    const [currentDir, setCurrentDir] = useState<DirItem | null>(null);
    const [exportModalVisible, setExportModalVisible] = useState(false);
    const [exportItem, setExportItem] = useState<DirItem | null>(null);
    const [importModalVisible, setImportModalVisible] = useState(false);
    const [importTargetDir, setImportTargetDir] = useState<DirItem | null>(null);
    const activeCanvasType =
      selectedCanvasType || (isCanvasType(newItemType) ? newItemType : undefined);
    const isCreatingCanvas = modalAction !== 'edit' && isCanvasType(newItemType);
    const showNetworkTopologyConnectionTest =
      (isCreatingCanvas || modalAction === 'edit') &&
      activeCanvasType === 'networkTopology';

    useImperativeHandle(
      ref,
      () => ({
        clearSelection: () => {
          setSelectedKeys([]);
        },
        setSelectedKeys: (keys: React.Key[]) => {
          setSelectedKeys(keys);
        },
      }),
      []
    );

    const autoExpandAll = (
      items: DirItem[],
      keys: React.Key[] = []
    ): React.Key[] => {
      items.forEach((item) => {
        keys.push(item.id);
        if (item.children) {
          autoExpandAll(item.children, keys);
        }
      });
      return keys;
    };

    const showModal = (
      action: ModalAction,
      title: string,
      defaultValue = '',
      dir: DirItem | null = null,
      itemType: DirectoryType = 'directory'
    ) => {
      setModalAction(action);
      setModalTitle(title);

      const initialGroups =
        action === 'edit'
          ? dir?.groups || []
          : action === 'addChild'
            ? dir?.groups || []
            : [];
      const formData: any = {
        name: defaultValue,
        desc: action === 'edit' && dir ? dir.desc : '',
        groups: initialGroups,
        canvasType: isCanvasType(itemType) ? itemType : undefined,
        // 编辑网络拓扑时用占位符 `******` 兜底展示;若用户输入新 token 才覆盖。
        baseUrl: '',
        token: '',
      };

      form.setFieldsValue(formData);

      // 如果是新增操作且没有默认 groups，则设置为当前用户选中的分组
      if (action !== 'edit' && selectedGroup && !formData.groups?.length) {
        form.setFieldValue('groups', [selectedGroup.id]);
      }

      setCurrentDir(dir);
      setNewItemType(itemType);
      setModalVisible(true);

      // 编辑网络拓扑时拉详情填充 baseUrl/token_set(token 永远不返回明文)。
      if (
        action === 'edit' &&
        itemType === 'networkTopology' &&
        dir?.data_id
      ) {
        networkTopologyApi
          .getNetworkTopologyDetail(dir.data_id)
          .then((detail) => {
            form.setFieldsValue({
              baseUrl: detail.base_url ?? '',
              // 已配置 token 时显示占位符;空字符串表示未配置。
              token: detail.token_set ? '******' : '',
            });
          })
          .catch(() => undefined);
      }
    };

    const handleSubmit = async (values: FormValues) => {
      setSubmitLoading(true);
      try {
        const targetItemType =
          modalAction === 'edit'
            ? newItemType
            : isCanvasType(values.canvasType)
              ? values.canvasType
              : newItemType;

        if (modalAction === 'edit') {
          if (!currentDir) return;
          const updateData: Record<string, unknown> = {
            name: values.name,
            desc: values.desc,
            groups: values.groups,
          };
          // 网络拓扑编辑:支持改 base_url + 重置 token。
          // 占位符 `******` 或空串都表示不修改 token,后端会保留旧值。
          if (targetItemType === 'networkTopology') {
            if (values.baseUrl) updateData.base_url = values.baseUrl;
            if (values.token && values.token !== '******') {
              updateData.token = values.token;
            }
          }
          await updateItem(newItemType, currentDir.data_id, updateData);
          if (onDataUpdate) {
            const updatedItem = {
              ...currentDir,
              name: values.name,
              desc: values.desc,
            };
            onDataUpdate(updatedItem);
          }
        } else {
          const itemData: ItemData = {
            name: values.name,
            desc: values.desc,
            groups: values.groups,
          };
          if (targetItemType === 'screen') {
            itemData.view_sets = buildDefaultScreenViewSets();
          }
          if (targetItemType === 'networkTopology') {
            itemData.base_url = values.baseUrl;
            itemData.token = values.token;
          }
          if (modalAction === 'addChild' && currentDir?.data_id) {
            if (isCanvasType(targetItemType)) {
              itemData.directory = parseInt(currentDir.data_id, 10);
            } else if (targetItemType === 'directory') {
              itemData.parent = parseInt(currentDir.data_id, 10);
            }
          } else if (targetItemType === 'directory') {
            itemData.parent = null;
          }
          await createItem(targetItemType, itemData);
        }
        handleModalCancel();
        await loadDirectories();
      } catch (error) {
        console.error('Failed to handle form submission:', error);
      } finally {
        setSubmitLoading(false);
      }
    };

    const handleModalOk = async () => {
      let values;
      try {
        values = await form.validateFields();
      } catch {
        return;
      }
      try {
        await handleSubmit(values);
      } catch (error) {
        console.error('Modal action failed:', error);
      }
    };

    const handleTestNetworkConnection = async () => {
      const isEditNetworkTopology =
        modalAction === 'edit' &&
        newItemType === 'networkTopology' &&
        Boolean(currentDir?.data_id);

      try {
        const values = await form.validateFields(['baseUrl', 'token']);
        const baseUrl = typeof values.baseUrl === 'string' ? values.baseUrl.trim() : '';
        const token = typeof values.token === 'string' ? values.token.trim() : '';

        setConnectionTesting(true);
        if (isEditNetworkTopology && currentDir?.data_id) {
          const payload: { base_url?: string; token?: string } = {};
          if (baseUrl) payload.base_url = baseUrl;
          if (token && token !== '******') payload.token = token;
          await networkTopologyApi.testSavedConnection(currentDir.data_id, payload);
        } else {
          await networkTopologyApi.testConnection({
            base_url: baseUrl,
            token,
          });
        }
        message.success(t('opsAnalysisSidebar.connectionTestSuccess'));
      } catch (error) {
        const maybeValidationError = error as { errorFields?: unknown[] };
        if (!maybeValidationError?.errorFields) {
          console.error('Network topology connection test failed:', error);
          message.error(t('opsAnalysisSidebar.connectionTestFailed'));
        }
      } finally {
        setConnectionTesting(false);
      }
    };

    const handleModalCancel = () => {
      setModalVisible(false);
      form.resetFields();
      setCurrentDir(null);
      setConnectionTesting(false);
    };

    const handleSearch = (value: string) => setSearchTerm(value);

    const handleDelete = (item: DirItem) => {
      Modal.confirm({
        title: t('common.delConfirm'),
        content: t('common.delConfirmCxt'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        okButtonProps: { danger: true },
        centered: true,
        onOk: async () => {
          try {
            await deleteItem(item.type, item.data_id);
            loadDirectories();
          } catch (error) {
            console.error('Failed to delete directory:', error);
          }
        },
      });
    };

    const mapTypeToObjectType = (type: DirectoryType): ObjectType | null => {
      return getCanvasTypeMeta(type)?.objectType || null;
    };

    const handleExport = (item: DirItem) => {
      setExportItem(item);
      setExportModalVisible(true);
    };

    const handleImport = (dir: DirItem) => {
      setImportTargetDir(dir);
      setImportModalVisible(true);
    };

    const getDirectoryIcon = (type: DirectoryType) => {
      const meta = getCanvasTypeMeta(type);
      if (!meta) {
        return type === 'directory' ? <FolderOutlined className="mr-1" /> : '';
      }

      const className = 'mr-1 text-sm';
      const iconMap = {
        dashboard: <BarChartOutlined className={`${className} text-purple-600`} />,
        topology: <Icon type="tuoputu" className="mr-1" />,
        architecture: <ApartmentOutlined className={`${className} text-green-600`} />,
        screen: <DesktopOutlined className={`${className} text-cyan-600`} />,
        report: <FileTextOutlined className={`${className} text-orange-600`} />,
        networkTopology: <BranchesOutlined className={`${className} text-blue-600`} />,
      };
      return iconMap[meta.icon];
    };

    const renderCanvasTypeIcon = (type: CanvasType) => {
      const className = 'text-base';
      const iconMap = {
        dashboard: <BarChartOutlined className={`${className} text-purple-600`} />,
        topology: <Icon type="tuoputu" className={`${className} text-blue-600`} />,
        architecture: <ApartmentOutlined className={`${className} text-green-600`} />,
        screen: <DesktopOutlined className={`${className} text-cyan-600`} />,
        report: <FileTextOutlined className={`${className} text-orange-600`} />,
        networkTopology: <BranchesOutlined className={`${className} text-blue-600`} />,
      };
      return iconMap[type];
    };

    const hasChildren = (item: DirItem): boolean => {
      if (!item.children || item.children.length === 0) {
        return false;
      }

      return item.children.some(
        (child) =>
          isCanvasType(child.type) ||
          (child.type === 'directory' && hasChildren(child))
      );
    };

    const menuItemsFor = (
      item: DirItem,
      parentId: string | null = null,
    ): MoreActionsDropdownItem[] => {
      const isRoot = parentId === null;
      const isGroup = item.type === 'directory';
      const canDelete = item.type !== 'directory' || !hasChildren(item);
      const isBuiltIn = !!item.is_build_in;
      const isCatalogue = item.type === 'directory';
      const editPermission = isCatalogue ? 'EditCatalogue' : 'EditChart';
      const deletePermission = isCatalogue ? 'DeleteCatalogue' : 'DeleteChart';

      // 内置对象：只显示导出按钮（非目录），其余禁用
      if (isBuiltIn) {
        return [
          ...(!isGroup
            ? [{
              key: 'export',
              label: t('opsAnalysisSidebar.exportYaml'),
              onClick: () => handleExport(item),
            }]
            : []),
          { key: 'edit', label: t('common.edit'), disabled: true },
          { key: 'delete', label: t('common.delete'), disabled: true },
        ];
      }

      const items: MoreActionsDropdownItem[] = [];
      if (isGroup) {
        items.push(
          {
            key: 'add-canvas',
            label: t('opsAnalysisSidebar.addCanvas'),
            permission: 'AddChart',
            onClick: () => {
              if (!hasPermission(['AddChart'])) return;
              showModal(
                'addChild',
                t('opsAnalysisSidebar.addCanvas'),
                '',
                item,
                'dashboard',
              );
            },
          },
          {
            key: 'import',
            label: t('opsAnalysisSidebar.importYaml'),
            permission: 'AddChart',
            onClick: () => {
              if (!hasPermission(['AddChart'])) return;
              handleImport(item);
            },
          },
        );
      }
      if (isRoot) {
        items.push({
          key: 'addGroup',
          label: t('opsAnalysisSidebar.addGroup'),
          permission: 'AddCatalogue',
          onClick: () => {
            if (!hasPermission(['AddCatalogue'])) return;
            setNewItemType('directory');
            showModal(
              'addChild',
              t('opsAnalysisSidebar.addGroup'),
              '',
              item,
              'directory',
            );
          },
        });
      }
      items.push(
        {
          key: 'edit',
          label: t('common.edit'),
          permission: editPermission,
          onClick: () => {
            if (!hasPermission([editPermission])) return;
            showModal(
              'edit',
              item.type === 'directory'
                ? t('opsAnalysisSidebar.editGroup')
                : t(getCanvasTypeMeta(item.type)?.editLabelKey || 'common.edit'),
              item.name,
              item,
              item.type,
            );
          },
        },
        {
          key: 'delete',
          label: t('common.delete'),
          permission: deletePermission,
          disabled: !canDelete,
          onClick: () => {
            if (!hasPermission([deletePermission])) return;
            handleDelete(item);
          },
        },
      );
      if (!isGroup) {
        items.push({
          key: 'export',
          label: t('opsAnalysisSidebar.exportYaml'),
          onClick: () => handleExport(item),
        });
      }
      return items;
    };

    const buildTreeData = (
      items: DirItem[],
      parentId: string | null = null
    ): DataNode[] =>
      items.map((item) => ({
        key: item.id,
        data: { type: item.type },
        selectable: item.type !== 'directory',
        title: (
          <span className="flex justify-between items-center w-full py-1">
            <span
              className={`flex items-center min-w-0 flex-1 ${item.type === 'directory' ? 'cursor-default' : 'cursor-pointer'}`}
            >
              {getDirectoryIcon(item.type)}
              <EllipsisWithTooltip
                className="max-w-[126px] whitespace-nowrap overflow-hidden text-ellipsis"
                text={item.name || '--'}
              />
              {item.is_build_in && item.type === 'directory' && (
                <span className="ml-1 text-[10px] text-gray-400">({t('common.builtIn')})</span>
              )}
            </span>
            {(item.is_build_in && item.type === 'directory') ? (
              <span />
            ) : (
              <MoreActionsDropdown
                items={menuItemsFor(item, parentId)}
                placement="bottomLeft"
                stopPropagation
                buttonClassName="flex-shrink-0"
              />
            )}
          </span>
        ),
        children: item.children
          ? buildTreeData(item.children, item.id)
          : undefined,
      }));

    const filterDirRecursively = (
      items: DirItem[],
      term: string
    ): DirItem[] => {
      if (!term) return items;

      return items.reduce<DirItem[]>((filtered, item) => {
        const matchesName = item.name
          .toLowerCase()
          .includes(term.toLowerCase());
        const filteredChildren = item.children
          ? filterDirRecursively(item.children, term)
          : [];

        if (matchesName || filteredChildren.length > 0) {
          filtered.push({
            ...item,
            children:
              filteredChildren.length > 0 ? filteredChildren : undefined,
          });
        }

        return filtered;
      }, []);
    };

    const filteredDirs = useMemo(
      () => filterDirRecursively(dirs, searchTerm),
      [dirs, searchTerm]
    );

    useEffect(() => {
      if (!searchTerm) {
        setExpandedKeys(autoExpandAll(dirs));
      }
    }, [dirs]);

    useEffect(() => {
      if (searchTerm && filteredDirs.length > 0) {
        setExpandedKeys(autoExpandAll(filteredDirs));
      }
    }, [searchTerm, filteredDirs]);

    const findItemById = (
      items: DirItem[],
      id: string
    ): DirItem | undefined => {
      for (const item of items) {
        if (item.id === id) return item;
        if (item.children) {
          const found = findItemById(item.children, id);
          if (found) return found;
        }
      }
      return undefined;
    };

    // 根据data_id查找项目
    const findItemByDataId = (
      items: DirItem[],
      id: string
    ): DirItem | undefined => {
      for (const item of items) {
        if (item.id === id) return item;
        if (item.children) {
          const found = findItemByDataId(item.children, id);
          if (found) return found;
        }
      }
      return undefined;
    };

    // 根据URL参数选中对应项目
    const selectItemFromUrlParams = (items: DirItem[]) => {
      const urlType = searchParams.get('type');
      const urlId = searchParams.get('id');

      if (!urlType || !urlId) return;

      const item = findItemByDataId(items, urlId);
      if (
        item &&
        item.type === urlType &&
        isCanvasType(item.type)
      ) {
        setSelectedKeys([item.id]);
        if (onSelect) {
          onSelect(item.type, item);
        }
      }
    };

    const loadDirectories = async () => {
      try {
        setLoading(true);
        const data = await getDirectoryTree();
        setDirs(data);
        selectItemFromUrlParams(data);
      } catch (error) {
        console.error('Failed to load directories:', error);
      } finally {
        setLoading(false);
      }
    };

    useEffect(() => {
      loadDirectories();
    }, []);

    return (
      <div className="p-4 h-full flex flex-col">
        <h3 className="text-base font-semibold mb-4">
          {t('opsAnalysisSidebar.title')}
        </h3>
        <div className="flex items-center mb-4">
          <Input.Search
            placeholder={t('common.search')}
            allowClear
            className="flex-1"
            onSearch={handleSearch}
          />
          <PermissionWrapper requiredPermissions={['AddCatalogue']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              className="ml-2"
              onClick={() =>
                showModal('addRoot', t('opsAnalysisSidebar.addDir'))
              }
            />
          </PermissionWrapper>
        </div>

        <div className="overflow-auto flex-1">
          <Spin spinning={loading}>
            {filteredDirs.length > 0 ? (
              <Tree
                key={searchTerm}
                blockNode
                treeData={buildTreeData(filteredDirs)}
                expandedKeys={expandedKeys}
                selectedKeys={selectedKeys}
                onExpand={(keys) => setExpandedKeys(keys)}
                onSelect={(selectedKeys, info) => {
                  const selection = resolveSidebarTreeSelection({
                    selectedKeys,
                    nodeKey: info.node.key,
                    selected: info.selected,
                  });
                  setSelectedKeys(selection.selectedKeys);
                  if (onSelect && selection.navigationKey) {
                    const item = findItemById(
                      filteredDirs,
                      selection.navigationKey,
                    );
                    if (item && item.type !== 'directory') {
                      onSelect(item.type, item);
                    }
                  }
                }}
                className="bg-transparent"
                style={{ overflow: 'hidden' }}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Spin>
        </div>

        <Modal
          title={modalTitle}
          open={modalVisible}
          centered
          width={isCreatingCanvas ? 760 : 520}
          onCancel={handleModalCancel}
          footer={[
            showNetworkTopologyConnectionTest ? (
              <Button
                key="testConnection"
                onClick={handleTestNetworkConnection}
                loading={connectionTesting}
              >
                {t('opsAnalysisSidebar.testConnection')}
              </Button>
            ) : null,
            <Button key="cancel" onClick={handleModalCancel}>
              {t('common.cancel')}
            </Button>,
            <Button
              key="submit"
              type="primary"
              onClick={handleModalOk}
              loading={submitLoading}
            >
              {t('common.confirm')}
            </Button>,
          ]}
          styles={{
            body: {
              maxHeight: 'calc(100vh - 200px)',
              overflowY: 'auto',
            },
          }}
        >
          <Form
            form={form}
            className="mt-5"
            layout="vertical"
          >
            {isCreatingCanvas && (
              <Form.Item
                label={t('opsAnalysisSidebar.canvasType')}
                required
              >
                <Form.Item
                  name="canvasType"
                  noStyle
                  rules={[{ required: true, message: t('common.selectMsg') }]}
                >
                  <Input type="hidden" />
                </Form.Item>
                <div
                  role="radiogroup"
                  aria-label={t('opsAnalysisSidebar.canvasType')}
                  className="grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-3"
                >
                  {CANVAS_TYPES.map((canvasType) => {
                    const meta = getCanvasTypeMeta(canvasType)!;
                    const selected = activeCanvasType === canvasType;

                    return (
                      <button
                        key={canvasType}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => {
                          form.setFieldValue('canvasType', canvasType);
                          form.validateFields(['canvasType']).catch(() => undefined);
                          setNewItemType(canvasType);
                        }}
                        className={`group relative flex min-h-[104px] w-full cursor-pointer overflow-hidden rounded-md border px-3 py-3 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
                          selected
                            ? 'border-blue-500 bg-gradient-to-br from-blue-50 to-white shadow-[0_2px_8px_rgba(37,99,235,0.08)]'
                            : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-slate-50 hover:shadow-[0_2px_6px_rgba(15,23,42,0.05)]'
                        }`}
                      >
                        <span
                          aria-hidden="true"
                          className={`absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full text-[10px] transition-all ${
                            selected
                              ? 'scale-100 bg-blue-600 text-white opacity-100 shadow-sm'
                              : 'scale-90 bg-gray-100 text-transparent opacity-0'
                          }`}
                        >
                          <CheckOutlined />
                        </span>
                        <span className="block min-w-0 pr-6">
                          <span className="flex items-center gap-2.5">
                            <span
                              className={`flex h-8 w-8 flex-none items-center justify-center rounded-md border transition-colors ${
                                selected
                                  ? 'border-blue-100 bg-white shadow-sm'
                                  : 'border-gray-100 bg-gray-50 group-hover:border-blue-100 group-hover:bg-white'
                              }`}
                            >
                              {renderCanvasTypeIcon(canvasType)}
                            </span>
                            <span
                              className={`block text-sm font-semibold ${
                                selected ? 'text-blue-700' : 'text-gray-900'
                              }`}
                            >
                              {t(meta.nameKey)}
                            </span>
                          </span>
                          <span
                            className={`mt-2 block text-xs leading-5 ${
                              selected ? 'text-slate-600' : 'text-gray-500'
                            }`}
                          >
                            {t(meta.descriptionKey)}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </Form.Item>
            )}
            <Form.Item
              name="name"
              label={t('opsAnalysisSidebar.nameLabel')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('opsAnalysisSidebar.inputPlaceholder')} />
            </Form.Item>
            {showNetworkTopologyConnectionTest && (
              <>
                <Form.Item
                  name="baseUrl"
                  label={t('opsAnalysisSidebar.baseUrlLabel')}
                  rules={[
                    // 编辑模式下 baseUrl 可留空(表示不改);创建模式必填。
                    { required: isCreatingCanvas, message: t('common.inputMsg') },
                    { type: 'url', message: t('opsAnalysisSidebar.baseUrlFormat') },
                  ]}
                >
                  <Input
                    placeholder={t('opsAnalysisSidebar.baseUrlPlaceholder')}
                    allowClear
                  />
                </Form.Item>
                <Form.Item
                  name="token"
                  label={t('opsAnalysisSidebar.tokenLabel')}
                  style={{ marginBottom: 8 }}
                  // 占位符 `******` 在编辑模式代表「保持原 token」,空字符串
                  // 代表「未配置」;两者都不再强制 >=4 字符。
                  rules={[
                    {
                      required: isCreatingCanvas,
                      message: t('common.inputMsg'),
                    },
                    {
                      validator: (_rule, value) => {
                        if (!value) return Promise.resolve();
                        if (value === '******') return Promise.resolve();
                        if (value.length < 4) {
                          return Promise.reject(
                            new Error(t('opsAnalysisSidebar.tokenMinLength')),
                          );
                        }
                        return Promise.resolve();
                      },
                    },
                  ]}
                >
                  <Input.Password
                    placeholder={t('opsAnalysisSidebar.tokenPlaceholder')}
                    autoComplete="new-password"
                  />
                </Form.Item>
              </>
            )}
            <Form.Item
              name="groups"
              label={t('common.group')}
              rules={[
                {
                  required: true,
                  message: `${t('common.selectMsg')}${t('common.group')}`,
                },
              ]}
            >
              <GroupTreeSelect
                placeholder={`${t('common.selectMsg')}${t('common.group')}`}
                multiple={true}
                mode="ownership"
              />
            </Form.Item>
            {newItemType !== 'directory' && (
              <Form.Item name="desc" label={t('opsAnalysisSidebar.descLabel')}>
                <Input.TextArea
                  autoSize={{ minRows: 3 }}
                  placeholder={`${t('common.inputMsg')} ${t('opsAnalysisSidebar.descLabel')}`}
                />
              </Form.Item>
            )}
          </Form>
        </Modal>

        {exportItem && (
          <ExportModal
            visible={exportModalVisible}
            onCancel={() => {
              setExportModalVisible(false);
              setExportItem(null);
            }}
            objectType={mapTypeToObjectType(exportItem.type)!}
            objectId={parseInt(exportItem.data_id, 10)}
            objectName={exportItem.name}
          />
        )}

        <ImportModal
          visible={importModalVisible}
          onCancel={() => {
            setImportModalVisible(false);
            setImportTargetDir(null);
          }}
          targetDirectoryId={importTargetDir ? parseInt(importTargetDir.data_id, 10) : null}
          onSuccess={() => {
            loadDirectories();
          }}
        />
      </div>
    );
  }
);

Sidebar.displayName = 'Sidebar';
export default Sidebar;
