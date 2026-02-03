'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { message, Modal } from 'antd';
import type { UserDataType } from '@/app/system-manager/types/user';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useGroupApi } from '@/app/system-manager/api/group/index';
import { useUserInfoContext } from '@/context/userInfo';
import {
  ExtendedTreeDataNode,
  convertGroupsToTreeData,
  nodeExistsInTree,
  findNodeByKey,
  filterTreeBySearch,
  hasChildren,
} from '@/app/system-manager/utils/userTreeUtils';

interface UseTreeDataResult {
  treeData: ExtendedTreeDataNode[];
  filteredTreeData: ExtendedTreeDataNode[];
  treeLoading: boolean;
  treeSearchValue: string;
  selectedTreeKeys: React.Key[];
  fetchTreeData: () => Promise<void>;
  handleTreeSearchChange: (value: string) => void;
  handleTreeSelect: (selectedKeys: React.Key[], fetchUsersCallback: (params: any) => void, searchValue: string, pageSize: number) => void;
  setSelectedTreeKeys: React.Dispatch<React.SetStateAction<React.Key[]>>;
}

export function useTreeData(t: (key: string) => string): UseTreeDataResult {
  const [treeData, setTreeData] = useState<ExtendedTreeDataNode[]>([]);
  const [filteredTreeData, setFilteredTreeData] = useState<ExtendedTreeDataNode[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(true);
  const [treeSearchValue, setTreeSearchValue] = useState<string>('');
  const [selectedTreeKeys, setSelectedTreeKeys] = useState<React.Key[]>([]);

  const { getOrgTree } = useUserApi();

  const fetchTreeData = useCallback(async () => {
    try {
      setTreeLoading(true);
      const res = await getOrgTree();
      const convertedData = convertGroupsToTreeData(res);
      setTreeData(convertedData);
      setFilteredTreeData(convertedData);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setTreeLoading(false);
    }
  }, [getOrgTree, t]);

  const handleTreeSearchChange = useCallback((value: string) => {
    setTreeSearchValue(value);
    setFilteredTreeData(filterTreeBySearch(treeData, value));
  }, [treeData]);

  const handleTreeSelect = useCallback((
    selectedKeys: React.Key[],
    fetchUsersCallback: (params: any) => void,
    searchValue: string,
    pageSize: number
  ) => {
    if (selectedKeys.length === 0 || !nodeExistsInTree(filteredTreeData, selectedKeys[0])) {
      setSelectedTreeKeys([]);
      fetchUsersCallback({
        search: searchValue,
        page: 1,
        page_size: pageSize,
        group_id: undefined,
      });
    } else {
      const selectedNode = findNodeByKey(filteredTreeData, selectedKeys[0] as number);
      if (selectedNode && selectedNode.hasAuth === false) {
        return;
      }
      setSelectedTreeKeys(selectedKeys.map(Number));
      fetchUsersCallback({
        search: searchValue,
        page: 1,
        page_size: pageSize,
        group_id: selectedKeys[0] as number,
      });
    }
  }, [filteredTreeData]);

  useEffect(() => {
    fetchTreeData();
  }, []);

  return {
    treeData,
    filteredTreeData,
    treeLoading,
    treeSearchValue,
    selectedTreeKeys,
    fetchTreeData,
    handleTreeSearchChange,
    handleTreeSelect,
    setSelectedTreeKeys,
  };
}

interface UseUserTableResult {
  tableData: UserDataType[];
  loading: boolean;
  total: number;
  currentPage: number;
  pageSize: number;
  searchValue: string;
  selectedRowKeys: React.Key[];
  fetchUsers: (params?: any) => Promise<void>;
  handleUserSearch: (value: string) => void;
  handleTableChange: (page: number, pageSize: number) => void;
  handleDeleteUser: (key: string) => Promise<void>;
  handleBatchDelete: () => void;
  setSelectedRowKeys: React.Dispatch<React.SetStateAction<React.Key[]>>;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
}

export function useUserTable(
  t: (key: string) => string,
  selectedTreeKeys: React.Key[]
): UseUserTableResult {
  const [tableData, setTableData] = useState<UserDataType[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [total, setTotal] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [searchValue, setSearchValue] = useState<string>('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const { getUsersList, deleteUser } = useUserApi();
  const { confirm } = Modal;

  const fetchUsers = useCallback(async (params: any = {}) => {
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
        group_role_list: item.group_role_list || [],
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
  }, [getUsersList, selectedTreeKeys, t]);

  const handleUserSearch = useCallback((value: string) => {
    setSearchValue(value);
    fetchUsers({ search: value, page: currentPage, page_size: pageSize });
  }, [fetchUsers, currentPage, pageSize]);

  const handleTableChange = useCallback((page: number, newPageSize: number) => {
    setCurrentPage(page);
    setPageSize(newPageSize);
  }, []);

  const handleDeleteUser = useCallback(async (key: string) => {
    try {
      await deleteUser({ user_ids: [key] });
      fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
  }, [deleteUser, fetchUsers, searchValue, currentPage, pageSize, t]);

  const handleBatchDelete = useCallback(() => {
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
  }, [confirm, deleteUser, selectedRowKeys, fetchUsers, searchValue, currentPage, pageSize, t]);

  useEffect(() => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  }, [currentPage, pageSize, searchValue]);

  return {
    tableData,
    loading,
    total,
    currentPage,
    pageSize,
    searchValue,
    selectedRowKeys,
    fetchUsers,
    handleUserSearch,
    handleTableChange,
    handleDeleteUser,
    handleBatchDelete,
    setSelectedRowKeys,
    setCurrentPage,
  };
}

interface UseGroupManagementResult {
  addGroupModalOpen: boolean;
  addSubGroupModalOpen: boolean;
  addGroupLoading: boolean;
  addGroupFormRef: React.RefObject<any>;
  handleAddRootGroup: () => void;
  handleGroupAction: (action: string, groupKey: number) => Promise<void>;
  onAddGroup: () => Promise<void>;
  resetAddGroupForm: () => void;
  closeGroupModals: () => void;
}

export function useGroupManagement(
  t: (key: string) => string,
  treeData: ExtendedTreeDataNode[],
  selectedTreeKeys: React.Key[],
  searchValue: string,
  currentPage: number,
  pageSize: number,
  fetchTreeData: () => Promise<void>,
  fetchUsers: (params: any) => Promise<void>,
  setSelectedTreeKeys: React.Dispatch<React.SetStateAction<React.Key[]>>,
  setSelectedRowKeys: React.Dispatch<React.SetStateAction<React.Key[]>>,
  groupEditModalRef: React.RefObject<any>
): UseGroupManagementResult {
  const [addGroupModalOpen, setAddGroupModalOpen] = useState(false);
  const [addSubGroupModalOpen, setAddSubGroupModalOpen] = useState(false);
  const [addGroupLoading, setAddGroupLoading] = useState(false);
  const [currentParentGroupKey, setCurrentParentGroupKey] = useState<number | null>(null);

  const addGroupFormRef = useRef<any>(null);
  const { addTeamData, deleteTeam } = useGroupApi();
  const { refreshUserInfo } = useUserInfoContext();
  const { confirm } = Modal;

  const handleAddRootGroup = useCallback(() => {
    setCurrentParentGroupKey(null);
    setAddGroupModalOpen(true);
  }, []);

  const handleGroupAction = useCallback(async (action: string, groupKey: number) => {
    const node = findNodeByKey(treeData, groupKey);
    if (node && node.hasAuth === false) {
      return;
    }

    switch (action) {
      case 'addSubGroup':
        setCurrentParentGroupKey(groupKey);
        setAddSubGroupModalOpen(true);
        break;
      case 'edit':
        const editGroup = findNodeByKey(treeData, groupKey);
        if (editGroup) {
          groupEditModalRef.current?.showModal({
            type: 'edit',
            groupId: groupKey,
            groupName: editGroup.title as string,
            roleIds: editGroup.roleIds || [],
          });
        }
        break;
      case 'delete':
        const targetGroup = findNodeByKey(treeData, groupKey);
        if (targetGroup) {
          const groupHasChildren = hasChildren(targetGroup);
          const confirmContent = groupHasChildren
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
                await deleteTeam({ id: groupKey });
                message.success(t('common.delSuccess'));

                const isSelectedDeleted = selectedTreeKeys.includes(groupKey);
                await fetchTreeData();
                await refreshUserInfo();

                if (isSelectedDeleted) {
                  setSelectedTreeKeys([]);
                  setSelectedRowKeys([]);
                  fetchUsers({
                    search: searchValue,
                    page: currentPage,
                    page_size: pageSize,
                    group_id: undefined,
                  });
                }
              } catch {
                message.error(t('common.delFailed'));
              }
            },
          });
        }
        break;
    }
  }, [treeData, groupEditModalRef, confirm, deleteTeam, selectedTreeKeys, fetchTreeData, refreshUserInfo, setSelectedTreeKeys, setSelectedRowKeys, fetchUsers, searchValue, currentPage, pageSize, t]);

  const onAddGroup = useCallback(async () => {
    try {
      setAddGroupLoading(true);
      const values = await addGroupFormRef.current?.validateFields();
      await addTeamData({
        group_name: values.name,
        parent_group_id: currentParentGroupKey,
      });
      message.success(t('common.saveSuccess'));
      await fetchTreeData();
      await refreshUserInfo();
      setAddGroupModalOpen(false);
      setAddSubGroupModalOpen(false);
      addGroupFormRef.current?.resetFields();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setAddGroupLoading(false);
    }
  }, [addTeamData, currentParentGroupKey, fetchTreeData, refreshUserInfo, t]);

  const resetAddGroupForm = useCallback(() => {
    addGroupFormRef.current?.resetFields();
  }, []);

  const closeGroupModals = useCallback(() => {
    setAddGroupModalOpen(false);
    setAddSubGroupModalOpen(false);
    resetAddGroupForm();
  }, [resetAddGroupForm]);

  return {
    addGroupModalOpen,
    addSubGroupModalOpen,
    addGroupLoading,
    addGroupFormRef,
    handleAddRootGroup,
    handleGroupAction,
    onAddGroup,
    resetAddGroupForm,
    closeGroupModals,
  };
}
