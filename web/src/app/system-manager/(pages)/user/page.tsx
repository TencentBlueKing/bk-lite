"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Input, message, Modal, Button, Spin, Form } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import TopSection from '@/components/top-section';
import UserModal, { ModalRef } from './userModal';
import PasswordModal, { PasswordModalRef } from '@/app/system-manager/components/user/passwordModal';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import CustomTable from '@/components/custom-table';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useGroupApi } from '@/app/system-manager/api/group/index';
import { OriginalGroup } from '@/app/system-manager/types/group';
import { UserDataType, TableRowSelection } from '@/app/system-manager/types/user';
import PageLayout from '@/components/page-layout';
import PermissionWrapper from '@/components/permission';
import OperateModal from '@/components/operate-modal';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import styles from './index.module.scss';

import GroupTree from '@/app/system-manager/components/user/GroupTree';
import { createUserTableColumns } from '@/app/system-manager/components/user/tableColumns';

const { Search } = Input;

interface ExtendedTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
  children?: ExtendedTreeDataNode[];
}

const User: React.FC = () => {
  const [tableData, setTableData] = useState<UserDataType[]>([]);
  const [selectedTreeKeys, setSelectedTreeKeys] = useState<React.Key[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [searchValue, setSearchValue] = useState<string>('');
  const [treeSearchValue, setTreeSearchValue] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [total, setTotal] = useState<number>(0);
  const [treeData, setTreeData] = useState<ExtendedTreeDataNode[]>([]);
  const [filteredTreeData, setFilteredTreeData] = useState<ExtendedTreeDataNode[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [addGroupModalOpen, setAddGroupModalOpen] = useState(false);
  const [addSubGroupModalOpen, setAddSubGroupModalOpen] = useState(false);
  const [renameGroupModalOpen, setRenameGroupModalOpen] = useState(false);
  const [addGroupLoading, setAddGroupLoading] = useState(false);
  const [renameGroupLoading, setRenameGroupLoading] = useState(false);
  const [currentParentGroupKey, setCurrentParentGroupKey] = useState<number | null>(null);
  const [renameGroupKey, setRenameGroupKey] = useState<number | null>(null);

  const addGroupFormRef = useRef<any>(null);
  const renameGroupFormRef = useRef<any>(null);
  const userModalRef = useRef<ModalRef>(null);
  const passwordModalRef = useRef<PasswordModalRef>(null);

  const { clientData } = useClientData();
  const { t } = useTranslation();
  const { confirm } = Modal;
  const { getUsersList, getOrgTree, deleteUser } = useUserApi();
  const { addTeamData, updateGroup, deleteTeam } = useGroupApi();
  const { convertToLocalizedTime } = useLocalizedTime();

  const appIconMap = new Map(
    clientData
      .filter(item => item.icon)
      .map((item) => [item.name, item.icon as string])
  );

  const fetchUsers = async (params: any = {}) => {
    setLoading(true);
    try {
      const res = await getUsersList({
        group_id: params.group_id !== undefined ? params.group_id : selectedTreeKeys[0],
        ...params,
      });
      const data = res.users.map((item: UserDataType) => ({
        key: item.id,
        username: item.username,
        name: item.display_name,
        email: item.email,
        role: item.role,
        roles: item.roles || [],
        last_login: item.last_login,
      }));
      setTableData(data);
      setTotal(res.count);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchTreeData = async () => {
    try {
      const res = await getOrgTree();
      const convertedData = convertGroups(res);
      setTreeData(convertedData);
      setFilteredTreeData(convertedData);
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  const convertGroups = (groups: OriginalGroup[]): ExtendedTreeDataNode[] => {
    return groups.map((group) => ({
      key: group.id,
      title: group.name,
      hasAuth: group.hasAuth,
      children: group.subGroups ? convertGroups(group.subGroups) : [],
    }));
  };

  const handleDeleteUser = async (key: string) => {
    try {
      await deleteUser({ user_ids: [key] });
      fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const columns = createUserTableColumns({
    t,
    appIconMap,
    convertToLocalizedTime,
    onEditUser: (userId: string) => {
      userModalRef.current?.showModal({ type: 'edit', userId });
    },
    onOpenPasswordModal: (userId: string) => {
      passwordModalRef.current?.showModal({ userId });
    },
    onDeleteUser: handleDeleteUser,
  });

  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const rowSelection: TableRowSelection<any> = {
    selectedRowKeys,
    onChange: onSelectChange,
  };

  const nodeExistsInTree = (tree: ExtendedTreeDataNode[], key: React.Key): boolean => {
    for (const node of tree) {
      if (node.key === key) return true;
      if (node.children && node.children.length > 0) {
        if (nodeExistsInTree(node.children, key)) return true;
      }
    }
    return false;
  };

  const findNode = (tree: ExtendedTreeDataNode[], key: number): ExtendedTreeDataNode | undefined => {
    for (const node of tree) {
      if (node.key === key) return node;
      if (node.children) {
        const found = findNode(node.children, key);
        if (found) return found;
      }
    }
  };

  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    setSelectedRowKeys([]);
    setCurrentPage(1);
    
    if (selectedKeys.length === 0 || !nodeExistsInTree(filteredTreeData, selectedKeys[0])) {
      setSelectedTreeKeys([]);
      fetchUsers({
        search: searchValue,
        page: 1,
        page_size: pageSize,
        group_id: undefined,
      });
    } else {
      const selectedNode = findNode(filteredTreeData, selectedKeys[0] as number);
      if (selectedNode && selectedNode.hasAuth === false) {
        return;
      }
      setSelectedTreeKeys(selectedKeys.map(Number));
      fetchUsers({
        search: searchValue,
        page: 1,
        page_size: pageSize,
        group_id: selectedKeys[0] as number,
      });
    }
  };

  const handleTreeSearchChange = (value: string) => {
    setTreeSearchValue(value);
    const filterFunc = (data: ExtendedTreeDataNode[], searchQuery: string): ExtendedTreeDataNode[] => {
      return data.reduce<ExtendedTreeDataNode[]>((acc, item) => {
        const children = item.children ? filterFunc(item.children, searchQuery) : [];
        if ((item.title as string).toLowerCase().includes(searchQuery.toLowerCase()) || children.length) {
          acc.push({ ...item, children });
        }
        return acc;
      }, []);
    };
    setFilteredTreeData(filterFunc(treeData, value));
  };

  const handleUserSearch = (value: string) => {
    setSearchValue(value);
    fetchUsers({ search: value, page: currentPage, page_size: pageSize });
  };

  const handleTableChange = (page: number, pageSize: number) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  };

  const handleModifyDelete = () => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      async onOk() {
        try {
          await deleteUser({ user_ids: selectedRowKeys });
          setSelectedRowKeys([]);
          fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleAddRootGroup = () => {
    setCurrentParentGroupKey(null);
    setAddGroupModalOpen(true);
  };

  const handleGroupAction = async (action: string, groupKey: number) => {
    const node = findNode(treeData, groupKey);
    if (node && node.hasAuth === false) {
      return;
    }

    switch (action) {
      case 'addSubGroup':
        setCurrentParentGroupKey(groupKey);
        setAddSubGroupModalOpen(true);
        break;
      case 'rename':
        const group = findNode(treeData, groupKey);
        if (group) {
          setRenameGroupKey(groupKey);
          setRenameGroupModalOpen(true);
        }
        break;
      case 'delete':
        const targetGroup = findNode(treeData, groupKey);
        if (targetGroup) {
          const hasChildren = targetGroup.children && targetGroup.children.length > 0;
          const confirmContent = hasChildren 
            ? t('system.group.deleteWithChildrenWarning') + '' + t('common.delConfirmCxt')
            : t('common.delConfirmCxt');
            
          confirm({
            title: t('common.delConfirm'),
            content: confirmContent,
            centered: true,
            okText: t('common.confirm'),
            cancelText: t('common.cancel'),
            async onOk() {
              try {
                setLoading(true);
                await deleteTeam({ id: groupKey });
                message.success(t('common.delSuccess'));
                
                const isSelectedDeleted = selectedTreeKeys.includes(groupKey);
                await fetchTreeData();
                
                if (isSelectedDeleted) {
                  setSelectedTreeKeys([]);
                  setSelectedRowKeys([]);
                  fetchUsers({ 
                    search: searchValue, 
                    page: currentPage, 
                    page_size: pageSize,
                    group_id: undefined
                  });
                }
              } catch {
                message.error(t('common.delFailed'));
              } finally {
                setLoading(false);
              }
            },
          });
        }
        break;
    }
  };

  const onAddGroup = async () => {
    try {
      setAddGroupLoading(true);
      const values = await addGroupFormRef.current?.validateFields();
      await addTeamData({
        group_name: values.name,
        parent_group_id: currentParentGroupKey,
      });
      message.success(t('common.saveSuccess'));
      await fetchTreeData();
      setAddGroupModalOpen(false);
      setAddSubGroupModalOpen(false);
      addGroupFormRef.current?.resetFields();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setAddGroupLoading(false);
    }
  };

  const onRenameGroup = async () => {
    if (!renameGroupKey) return;
    try {
      setRenameGroupLoading(true);
      const values = await renameGroupFormRef.current?.validateFields();
      await updateGroup({
        group_id: renameGroupKey,
        group_name: values.renameTeam,
      });
      message.success(t('system.group.renameSuccess'));
      await fetchTreeData();
      setRenameGroupModalOpen(false);
      renameGroupFormRef.current?.resetFields();
    } catch {
      message.error(t('system.group.renameFailed'));
    } finally {
      setRenameGroupLoading(false);
    }
  };

  const resetAddGroupForm = () => {
    addGroupFormRef.current?.resetFields();
  };

  const resetRenameGroupForm = () => {
    renameGroupFormRef.current?.resetFields();
  };

  const openUserModal = (type: 'add') => {
    userModalRef.current?.showModal({
      type,
      groupKeys: type === 'add' ? selectedTreeKeys.map(Number) : [],
    });
  };

  const onSuccessUserModal = () => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  };

  useEffect(() => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  }, [currentPage, pageSize, searchValue]);

  useEffect(() => {
    fetchTreeData();
  }, []);

  const isDeleteDisabled = selectedRowKeys.length === 0;

  return (
    <>
      <PageLayout
        topSection={<TopSection title={t('system.user.title')} content={t('system.user.desc')} />}
        leftSection={
          <div className={`w-full h-full flex flex-col ${styles.userInfo}`}>
            <GroupTree
              treeData={filteredTreeData}
              searchValue={treeSearchValue}
              onSearchChange={handleTreeSearchChange}
              onAddRootGroup={handleAddRootGroup}
              onTreeSelect={handleTreeSelect}
              onGroupAction={handleGroupAction}
              t={t}
            />
          </div>
        }
        rightSection={
          <>
            <div className="w-full mb-4 flex justify-end">
              <Search
                allowClear
                enterButton
                className="w-60 mr-2"
                onSearch={handleUserSearch}
                placeholder={`${t('common.search')}...`}
              />
              <PermissionWrapper requiredPermissions={['Add User']}>
                <Button type="primary" className="mr-2" onClick={() => openUserModal('add')}>
                  +{t('common.add')}
                </Button>
              </PermissionWrapper>
              <UserModal ref={userModalRef} treeData={treeData} onSuccess={onSuccessUserModal} />
              <PermissionWrapper requiredPermissions={['Delete User']}>
                <Button onClick={handleModifyDelete} disabled={isDeleteDisabled}>
                  {t('common.batchDelete')}
                </Button>
              </PermissionWrapper>
              <PasswordModal 
                ref={passwordModalRef} 
                onSuccess={() => fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize })} 
              />
            </div>
            <Spin spinning={loading}>
              <CustomTable
                scroll={{ y: 'calc(100vh - 360px)' }}
                pagination={{
                  pageSize,
                  current: currentPage,
                  total,
                  showSizeChanger: true,
                  onChange: handleTableChange,
                }}
                columns={columns}
                dataSource={tableData}
                rowSelection={rowSelection}
              />
            </Spin>
          </>
        }
      />
      
      <OperateModal
        title={t('common.add')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: addGroupLoading }}
        cancelButtonProps={{ disabled: addGroupLoading }}
        open={addGroupModalOpen || addSubGroupModalOpen}
        onOk={onAddGroup}
        onCancel={() => {
          setAddGroupModalOpen(false);
          setAddSubGroupModalOpen(false);
          resetAddGroupForm();
        }}
        destroyOnClose={true}
      >
        <Form ref={addGroupFormRef}>
          <Form.Item
            name="name"
            label={t('system.group.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.group.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>

      <OperateModal
        title={t('system.group.rename')}
        closable={false}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ loading: renameGroupLoading }}
        cancelButtonProps={{ disabled: renameGroupLoading }}
        open={renameGroupModalOpen}
        onOk={onRenameGroup}
        onCancel={() => {
          setRenameGroupModalOpen(false);
          resetRenameGroupForm();
        }}
        destroyOnClose={true}
      >
        <Form ref={renameGroupFormRef}>
          <Form.Item
            name="renameTeam"
            label={t('system.user.form.name')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.name')}`} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
};

export default User;
