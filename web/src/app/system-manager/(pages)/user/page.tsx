"use client";
import React, { useState, useEffect, useRef } from 'react';
import { Input, message, Modal, Tree, Button, Spin, Popconfirm } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { ColumnsType } from 'antd/es/table';
import TopSection from '@/components/top-section';
import UserModal, { ModalRef } from './userModal';
import PasswordModal, { PasswordModalRef } from '@/app/system-manager/components/user/passwordModal';
import { useTranslation } from '@/utils/i18n';
import { getRandomColor } from '@/app/system-manager/utils';
import CustomTable from '@/components/custom-table';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { OriginalGroup } from '@/app/system-manager/types/group';
import { UserDataType, TableRowSelection } from '@/app/system-manager/types/user';
import PageLayout from '@/components/page-layout';
import styles from './index.module.scss'

const { Search } = Input;

const User: React.FC = () => {
  const [tableData, setTableData] = useState<UserDataType[]>([]);
  const [selectedTreeKeys, setSelectedTreeKeys] = useState<React.Key[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [isDeleteDisabled, setIsDeleteDisabled] = useState<boolean>(true);
  const [searchValue, setSearchValue] = useState<string>('');
  const [treeSearchValue, setTreeSearchValue] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [total, setTotal] = useState<number>(0);
  const [treeData, setTreeData] = useState<TreeDataNode[]>([]);
  const [filteredTreeData, setFilteredTreeData] = useState<TreeDataNode[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const userModalRef = useRef<ModalRef>(null);
  const passwordModalRef = useRef<PasswordModalRef>(null);

  const { t } = useTranslation();
  const { confirm } = Modal;
  const { getUsersList, getOrgTree, deleteUser } = useUserApi();

  const columns: ColumnsType<UserDataType> = [
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      width: 230,
      fixed: 'left',
      render: (text: string) => {
        const color = getRandomColor();
        return (
          <div className="flex" style={{ height: '17px', lineHeight: '17px' }}>
            <span
              className="h-5 w-5 rounded-[10px] text-center mr-1"
              style={{ color: '#ffffff', backgroundColor: color }}
            >
              {text?.substring(0, 1)}
            </span>
            <span>{text}</span>
          </div>
        );
      },
    },
    {
      title: t('system.user.table.lastName'),
      dataIndex: 'name',
      width: 100,
    },
    {
      title: t('system.user.table.email'),
      dataIndex: 'email',
      width: 185,
    },
    {
      title: t('common.actions'),
      dataIndex: 'key',
      width: 160,
      fixed: 'right',
      render: (key: string) => (
        <>
          <Button type="link" className="mr-[8px]" onClick={() => handleEditUser(key)}>
            {t('common.edit')}
          </Button>
          <Button type="link" className="mr-[8px]" onClick={() => openPasswordModal(key)}>
            {t('system.common.password')}
          </Button>
          <Popconfirm
            title={t('common.delConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={() => showDeleteConfirm(key)}
          >
            <Button type="link">{t('common.delete')}</Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  const fetchUsers = async (params: any = {}) => {
    setLoading(true);
    try {
      const res = await getUsersList({
        group_id: selectedTreeKeys[0],
        ...params,
      });
      const data = res.users.map((item: UserDataType) => ({
        key: item.id,
        username: item.username,
        name: item.lastName,
        email: item.email,
        role: item.role,
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
      setTreeData(convertGroups(res));
      setFilteredTreeData(convertGroups(res));
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  useEffect(() => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  }, [currentPage, pageSize, searchValue]);

  useEffect(() => {
    fetchTreeData();
  }, []);

  useEffect(() => {
    setIsDeleteDisabled(selectedRowKeys.length === 0);
  }, [selectedRowKeys]);

  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    setSelectedRowKeys([]);
    setSelectedTreeKeys(selectedKeys);
    fetchUsers({
      search: searchValue,
      page: currentPage,
      page_size: pageSize,
      group_id: selectedKeys[0],
    });
  };

  const handleEditUser = (userId: string) => {
    userModalRef.current?.showModal({ type: 'edit', userId });
  };

  const openPasswordModal = (userId: string) => {
    passwordModalRef.current?.showModal({ userId });
  };

  const convertGroups = (groups: OriginalGroup[]): TreeDataNode[] => {
    return groups.map((group) => ({
      key: group.id,
      title: group.name,
      children: group.subGroups ? convertGroups(group.subGroups) : [],
    }));
  };

  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const rowSelection: TableRowSelection<any> = {
    selectedRowKeys,
    onChange: onSelectChange,
  };

  const showDeleteConfirm = async (key: string) => {
    try {
      await deleteUser({ user_ids: [key] });
      fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
      message.success(t('common.delSuccess'));
    } catch {
      message.error(t('common.delFailed'));
    }
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

  const openUserModal = (type: 'add') => {
    userModalRef.current?.showModal({
      type,
      groupKeys: type === 'add' ? (selectedTreeKeys as string[]) : [],
    });
  };

  const onSuccessUserModal = () => {
    fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize });
  };

  const handleTreeSearchChange = (value: string) => {
    setTreeSearchValue(value);
    filterTreeData(value);
  };

  const handleUserSearch = (value: string) => {
    setSearchValue(value);
    fetchUsers({ search: value, page: currentPage, page_size: pageSize });
  };

  const filterTreeData = (value: string) => {
    const filterFunc = (data: TreeDataNode[], searchQuery: string): TreeDataNode[] => {
      return data.reduce<TreeDataNode[]>((acc, item) => {
        const children = item.children ? filterFunc(item.children, searchQuery) : [];
        if ((item.title as string).toLowerCase().includes(searchQuery.toLowerCase()) || children.length) {
          acc.push({ ...item, children });
        }
        return acc;
      }, []);
    };
    setFilteredTreeData(filterFunc(treeData, value));
  };

  const handleTableChange = (page: number, pageSize: number) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  };

  const topSectionContent = (
    <TopSection title={t('system.user.title')} content={t('system.user.desc')} />
  );

  const leftSectionContent = (
    <div className={`w-full h-full flex flex-col ${styles.userInfo}`}>
      <Input
        className="w-full"
        placeholder={`${t('common.search')}...`}
        onChange={(e) => handleTreeSearchChange(e.target.value)}
        value={treeSearchValue}
      />
      <Tree
        className="w-full flex-1 mt-4 overflow-auto"
        showLine
        expandAction={false}
        defaultExpandAll
        treeData={filteredTreeData}
        onSelect={handleTreeSelect}
      />
    </div>
  );

  const rightSectionContent = (
    <>
      <div className="w-full mb-4 flex justify-end">
        <Search
          allowClear
          enterButton
          className="w-60 mr-2"
          onSearch={handleUserSearch}
          placeholder={`${t('common.search')}...`}
        />
        <Button type="primary" className="mr-2" onClick={() => openUserModal('add')}>
          +{t('common.add')}
        </Button>
        <UserModal ref={userModalRef} treeData={treeData} onSuccess={onSuccessUserModal} />
        <Button onClick={handleModifyDelete} disabled={isDeleteDisabled}>
          {t('common.batchDelete')}
        </Button>
        <PasswordModal ref={passwordModalRef} onSuccess={() => fetchUsers({ search: searchValue, page: currentPage, page_size: pageSize })} />
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
  );

  return (
    <PageLayout
      topSection={topSectionContent}
      leftSection={leftSectionContent}
      rightSection={rightSectionContent}
    />
  );
};

export default User;
