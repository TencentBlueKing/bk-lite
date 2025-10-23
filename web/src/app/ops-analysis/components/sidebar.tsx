'use client';

import React, {
  useState,
  useMemo,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import Icon from '@/components/icon';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { DataNode } from 'antd/lib/tree';
import { Form } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { Input, Button, Modal, Dropdown, Menu, Tree, Empty, Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useDirectoryApi } from '@/app/ops-analysis/api/index';
import {
  SidebarProps,
  SidebarRef,
  DirItem,
  ModalAction,
  DirectoryType,
} from '@/app/ops-analysis/types';
import {
  PlusOutlined,
  MoreOutlined,
  BarChartOutlined,
  SettingOutlined,
  FolderOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';

const Sidebar = forwardRef<SidebarRef, SidebarProps>(
  ({ onSelect, onDataUpdate }, ref) => {
    const [form] = Form.useForm();
    const { t } = useTranslation();
    const searchParams = useSearchParams();
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
      form.setFieldsValue({
        name: defaultValue,
        desc: action === 'edit' && dir ? dir.desc : '',
      });
      setCurrentDir(dir);
      setNewItemType(itemType);
      setModalVisible(true);
    };

    const handleSubmit = async (values: any) => {
      setSubmitLoading(true);
      try {
        if (modalAction === 'edit') {
          if (!currentDir) return;
          const updateData = {
            name: values.name,
            desc: values.desc,
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
          const itemData: any = {
            name: values.name,
            desc: values.desc,
          };
          if (modalAction === 'addChild' && currentDir?.data_id) {
            if (
              ['dashboard', 'topology', 'architecture'].includes(newItemType)
            ) {
              itemData.directory = parseInt(currentDir.data_id, 10);
            } else if (newItemType === 'directory') {
              itemData.parent_id = parseInt(currentDir.data_id, 10);
            }
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

      return (
        <Menu selectable={false}>
          {isGroup && (
            <>
              <Menu.Item
                key="addDashboard"
                onClick={() => {
                  setNewItemType('dashboard');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addDash'),
                    '',
                    item,
                    'dashboard'
                  );
                }}
              >
                {t('opsAnalysisSidebar.addDash')}
              </Menu.Item>
              <Menu.Item
                key="addTopology"
                onClick={() => {
                  setNewItemType('topology');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addTopo'),
                    '',
                    item,
                    'topology'
                  );
                }}
              >
                {t('opsAnalysisSidebar.addTopo')}
              </Menu.Item>
              <Menu.Item
                key="addArchitecture"
                onClick={() => {
                  setNewItemType('architecture');
                  showModal(
                    'addChild',
                    t('opsAnalysisSidebar.addArch'),
                    '',
                    item,
                    'architecture'
                  );
                }}
              >
                {t('opsAnalysisSidebar.addArch')}
              </Menu.Item>
            </>
          )}
          {isRoot && (
            <Menu.Item
              key="addGroup"
              onClick={() => {
                setNewItemType('directory');
                showModal(
                  'addChild',
                  t('opsAnalysisSidebar.addGroup'),
                  '',
                  item,
                  'directory'
                );
              }}
            >
              {t('opsAnalysisSidebar.addGroup')}
            </Menu.Item>
          )}

          <Menu.Item
            key="edit"
            onClick={() =>
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
                item.type
              )
            }
          >
            {t('common.edit')}
          </Menu.Item>

          <Menu.Item
            key="delete"
            disabled={!canDelete}
            onClick={() => handleDelete(item)}
          >
            {t('common.delete')}
          </Menu.Item>
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
            </span>
            <Dropdown
              overlay={menuFor(item, parentId)}
              trigger={['click']}
              placement="bottomLeft"
              getPopupContainer={() => document.body}
            >
              <Button
                type="text"
                icon={<MoreOutlined />}
                onClick={(e) => e.stopPropagation()}
                className="flex-shrink-0"
                size="small"
              />
            </Dropdown>
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
          <Button
            type="primary"
            icon={<PlusOutlined />}
            className="ml-2"
            onClick={() => showModal('addRoot', t('opsAnalysisSidebar.addDir'))}
          />
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
        <div className="flex justify-center height-[32px]">
          <Button
            block
            icon={<SettingOutlined />}
            onClick={() => {
              // 清空tree选中状态
              setSelectedKeys([]);
              // 调用父组件的onSelect
              onSelect && onSelect('settings');
            }}
          >
            设置
          </Button>
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
          <Form form={form} className="mt-5" labelCol={{ span: 3 }}>
            <Form.Item
              name="name"
              label={t('opsAnalysisSidebar.nameLabel')}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t('opsAnalysisSidebar.inputPlaceholder')} />
            </Form.Item>
            {newItemType !== 'directory' && (
              <Form.Item name="desc" label={t('opsAnalysisSidebar.descLabel')}>
                <Input.TextArea
                  autoSize={{ minRows: 3 }}
                  placeholder={t('common.inputMsg')}
                />
              </Form.Item>
            )}
          </Form>
        </Modal>
      </div>
    );
  }
);

Sidebar.displayName = 'Sidebar';
export default Sidebar;
