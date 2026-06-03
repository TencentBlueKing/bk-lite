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
import useBtnPermissions from '@/hooks/usePermissions';
import type { DataNode } from 'antd/lib/tree';
import { Form } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { Input, Button, Modal, Dropdown, Menu, Tree, Empty, Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useDirectoryApi } from '@/app/ops-analysis/api/index';
import { useUserInfoContext } from '@/context/userInfo';
import { ExportModal, ImportModal } from './importExport';
import { ObjectType } from '@/app/ops-analysis/api/importExport';
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
  MoreOutlined,
  BarChartOutlined,
  FolderOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';

const Sidebar = forwardRef<SidebarRef, SidebarProps>(
  ({ onSelect, onDataUpdate }, ref) => {
    const [form] = Form.useForm();
    const { t } = useTranslation();
    const searchParams = useSearchParams();
    const { selectedGroup } = useUserInfoContext();
    const { hasPermission } = useBtnPermissions();
    const [dirs, setDirs] = useState<DirItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [submitLoading, setSubmitLoading] = useState(false);
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

      const formData: any = {
        name: defaultValue,
        desc: action === 'edit' && dir ? dir.desc : '',
        groups: action === 'edit' && dir ? dir.groups || [] : [],
      };

      form.setFieldsValue(formData);

      // 如果是新增操作且没有默认 groups，则设置为当前用户选中的分组
      if (action !== 'edit' && selectedGroup && !formData.groups?.length) {
        form.setFieldValue('groups', [selectedGroup.id]);
      }

      setCurrentDir(dir);
      setNewItemType(itemType);
      setModalVisible(true);
    };

    const handleSubmit = async (values: FormValues) => {
      setSubmitLoading(true);
      try {
        if (modalAction === 'edit') {
          if (!currentDir) return;
          const updateData = {
            name: values.name,
            desc: values.desc,
            groups: values.groups,
          };
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
          if (modalAction === 'addChild' && currentDir?.data_id) {
            if (
              ['dashboard', 'topology', 'architecture'].includes(newItemType)
            ) {
              itemData.directory = parseInt(currentDir.data_id, 10);
            } else if (newItemType === 'directory') {
              itemData.parent = parseInt(currentDir.data_id, 10);
            }
          } else if (newItemType === 'directory') {
            itemData.parent = null;
          }
          await createItem(newItemType, itemData);
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
        handleSubmit(values);
      } catch (error) {
        console.error('Modal action failed:', error);
      }
    };

    const handleModalCancel = () => {
      setModalVisible(false);
      form.resetFields();
      setCurrentDir(null);
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
      const typeMap: Record<string, ObjectType> = {
        dashboard: 'dashboard',
        topology: 'topology',
        architecture: 'architecture',
      };
      return typeMap[type] || null;
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
      switch (type) {
        case 'dashboard':
          return <BarChartOutlined className="mr-1 text-purple-600" />;
        case 'topology':
          return <Icon type="tuoputu" className="mr-1" />;
        case 'architecture':
          return <ApartmentOutlined className="mr-1 text-green-600 text-sm" />;
        case 'directory':
          return <FolderOutlined className="mr-1" />;
        default:
          return '';
      }
    };

    const hasChildren = (item: DirItem): boolean => {
      if (!item.children || item.children.length === 0) {
        return false;
      }

      return item.children.some(
        (child) =>
          child.type === 'dashboard' ||
          child.type === 'topology' ||
          child.type === 'architecture' ||
          (child.type === 'directory' && hasChildren(child))
      );
    };

    const menuFor = (item: DirItem, parentId: string | null = null) => {
      const isRoot = parentId === null;
      const isGroup = item.type === 'directory';
      const canDelete = item.type !== 'directory' || !hasChildren(item);
      const isBuiltIn = !!item.is_build_in;

      const stopEventPropagation = (event?: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement> | Event) => {
        event?.stopPropagation?.();
      };

      // 根据 item.type 确定需要的权限
      const isCatalogue = item.type === 'directory';
      const editPermission = isCatalogue ? 'EditCatalogue' : 'EditChart';
      const deletePermission = isCatalogue ? 'DeleteCatalogue' : 'DeleteChart';

      // 内置对象：只显示导出按钮（非目录），其余禁用
      if (isBuiltIn) {
        return (
          <Menu selectable={false}>
            {!isGroup && (
              <Menu.Item
                key="export"
                onClick={(e) => {
                  stopEventPropagation(e.domEvent);
                  handleExport(item);
                }}
              >
                {t('opsAnalysisSidebar.exportYaml')}
              </Menu.Item>
            )}
            <Menu.Item key="edit" disabled>
              {t('common.edit')}
            </Menu.Item>
            <Menu.Item key="delete" disabled>
              {t('common.delete')}
            </Menu.Item>
          </Menu>
        );
      }

      return (
        <Menu selectable={false}>
          {isGroup && (
            <>
              <Menu.Item
                key="addDashboard"
                onClick={(e) => {
                  stopEventPropagation(e.domEvent);
                  if (!hasPermission(['AddChart'])) return;
                  setNewItemType('dashboard');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addDash'),
                    '',
                    item,
                    'dashboard',
                  );
                }}
              >
                <PermissionWrapper requiredPermissions={['AddChart']}>
                  {t('opsAnalysisSidebar.addDash')}
                </PermissionWrapper>
              </Menu.Item>
              <Menu.Item
                key="addTopology"
                onClick={(e) => {
                  stopEventPropagation(e.domEvent);
                  if (!hasPermission(['AddChart'])) return;
                  setNewItemType('topology');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addTopo'),
                    '',
                    item,
                    'topology',
                  );
                }}
              >
                <PermissionWrapper requiredPermissions={['AddChart']}>
                  {t('opsAnalysisSidebar.addTopo')}
                </PermissionWrapper>
              </Menu.Item>
              <Menu.Item
                key="addArchitecture"
                onClick={(e) => {
                  stopEventPropagation(e.domEvent);
                  if (!hasPermission(['AddChart'])) return;
                  setNewItemType('architecture');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addArch'),
                    '',
                    item,
                    'architecture',
                  );
                }}
              >
                <PermissionWrapper requiredPermissions={['AddChart']}>
                  {t('opsAnalysisSidebar.addArch')}
                </PermissionWrapper>
              </Menu.Item>
              <Menu.Item
                key="import"
                onClick={(e) => {
                  stopEventPropagation(e.domEvent);
                  if (!hasPermission(['AddChart'])) return;
                  handleImport(item);
                }}
              >
                <PermissionWrapper requiredPermissions={['AddChart']}>
                  {t('opsAnalysisSidebar.importYaml')}
                </PermissionWrapper>
              </Menu.Item>
            </>
          )}
          {isRoot && (
            <Menu.Item
              key="addGroup"
              onClick={(e) => {
                stopEventPropagation(e.domEvent);
                if (!hasPermission(['AddCatalogue'])) return;
                setNewItemType('directory');
                showModal(
                  'addChild',
                  t('opsAnalysisSidebar.addGroup'),
                  '',
                  item,
                  'directory',
                );
              }}
            >
              <PermissionWrapper requiredPermissions={['AddCatalogue']}>
                {t('opsAnalysisSidebar.addGroup')}
              </PermissionWrapper>
            </Menu.Item>
          )}

          <Menu.Item
            key="edit"
            onClick={(e) => {
              stopEventPropagation(e.domEvent);
              if (!hasPermission([editPermission])) return;
              showModal(
                'edit',
                item.type === 'directory'
                  ? t('opsAnalysisSidebar.editGroup')
                  : item.type === 'dashboard'
                    ? t('opsAnalysisSidebar.editDash')
                    : item.type === 'topology'
                      ? t('opsAnalysisSidebar.editTopo')
                      : t('opsAnalysisSidebar.editArch'),
                item.name,
                item,
                item.type,
              );
            }}
          >
            <PermissionWrapper requiredPermissions={[editPermission]}>
              {t('common.edit')}
            </PermissionWrapper>
          </Menu.Item>

          <Menu.Item
            key="delete"
            disabled={!canDelete}
            onClick={(e) => {
              stopEventPropagation(e.domEvent);
              if (!hasPermission([deletePermission])) return;
              handleDelete(item);
            }}
          >
            <PermissionWrapper requiredPermissions={[deletePermission]}>
              {t('common.delete')}
            </PermissionWrapper>
          </Menu.Item>

          {!isGroup && (
            <Menu.Item
              key="export"
              onClick={(e) => {
                stopEventPropagation(e.domEvent);
                handleExport(item);
              }}
            >
              {t('opsAnalysisSidebar.exportYaml')}
            </Menu.Item>
          )}
        </Menu>
      );
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
              <Dropdown
                overlay={menuFor(item, parentId)}
                trigger={['click']}
                placement="bottomLeft"
                getPopupContainer={() => document.body}
              >
                <Button
                  type="text"
                  aria-label={t('common.more')}
                  icon={<MoreOutlined aria-hidden="true" />}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                  className="flex-shrink-0"
                  size="small"
                />
              </Dropdown>
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
        (item.type === 'dashboard' ||
          item.type === 'topology' ||
          item.type === 'architecture')
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
                  const key = (selectedKeys as string[])[0];
                  setSelectedKeys(selectedKeys);
                  if (onSelect && key && info.selectedNodes.length > 0) {
                    const item = findItemById(filteredDirs, key);
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
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          style={{ top: '35%' }}
          onOk={handleModalOk}
          onCancel={handleModalCancel}
          confirmLoading={submitLoading}
        >
          <Form form={form} className="mt-5" labelCol={{ span: 5 }}>
            <Form.Item
              name="name"
              label={t('opsAnalysisSidebar.nameLabel')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('opsAnalysisSidebar.inputPlaceholder')} />
            </Form.Item>
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
