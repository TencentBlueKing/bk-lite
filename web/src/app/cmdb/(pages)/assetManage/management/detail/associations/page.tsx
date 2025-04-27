'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Button, Modal, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import AssociationsModal from './associationsModal';
import { Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { CONSTRAINT_List } from '@/app/cmdb/constants/asset';
import useApiClient from '@/utils/request';
import { ModelItem, AssoTypeItem, GroupItem } from '@/app/cmdb/types/assetManage';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { deepClone } from '@/app/cmdb/utils/common';
import { useCommon } from '@/app/cmdb/context/common';
import PermissionWrapper from '@/components/permission';

const { confirm } = Modal;

const Associations = () => {
  const { get, del } = useApiClient();
  const searchParams = useSearchParams();
  const modelId = searchParams.get('model_id');
  const { t } = useTranslation();
  const commonContext = useCommon();
  const permissionGroupsInfo = useRef(
    commonContext?.permissionGroupsInfo || null
  );
  const isAdmin = permissionGroupsInfo.current?.is_all;
  const assoRef = useRef<any>(null);
  const [searchText, setSearchText] = useState<string>('');
  const [pagination, setPagination] = useState<any>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<any[]>([]);
  const [modelList, setModelList] = useState<ModelItem[]>([]);
  const [assoTypeList, setAssoTypeList] = useState<AssoTypeItem[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const columns: TableColumnsType<any> = [
    {
      title: t('name'),
      dataIndex: 'model_asst_id',
      key: 'model_asst_id',
      ellipsis: {
        showTitle: false,
      },
      render: (_, record) => {
        const assoName = `${showModelName(record.src_model_id)}_${
          assoTypeList.find((item) => item.asst_id === record.asst_id)
            ?.asst_name || '--'
        }_${showModelName(record.dst_model_id)}`;
        return (
          <a
            title={assoName}
            onClick={() =>
              showAssoModal('edit', {
                ...record,
                subTitle: assoName,
              })
            }
          >
            {assoName}
          </a>
        );
      },
    },
    {
      title: t('Model.sourceModel'),
      dataIndex: 'src_model_id',
      key: 'src_model_id',
      render: (_, { src_model_id }) => <>{showModelName(src_model_id)}</>,
    },
    {
      title: t('Model.targetModel'),
      dataIndex: 'dst_model_id',
      key: 'dst_model_id',
      render: (_, { dst_model_id }) => <>{showModelName(dst_model_id)}</>,
    },
    {
      title: t('Model.constraint'),
      dataIndex: 'mapping',
      key: 'mapping',
      render: (_, { mapping }) => (
        <>{CONSTRAINT_List.find((item) => item.id === mapping)?.name || '--'}</>
      ),
    },
    {
      title: t('type'),
      key: 'asst_id',
      dataIndex: 'asst_id',
      render: (_, { asst_id }) => {
        return (
          <>
            {
              <Tag color="green">
                {assoTypeList.find((item) => item.asst_id === asst_id)
                  ?.asst_name || '--'}
              </Tag>
            }
          </>
        );
      },
    },
    {
      title: t('action'),
      key: 'action',
      render: (_, record) => (
        <>
          <Button
            type="link"
            disabled={!isAdmin && record.is_pre}
            onClick={() => showDeleteConfirm(record.model_asst_id)}
          >
            {t('delete')}
          </Button>
        </>
      ),
    },
  ];

  useEffect(() => {
    getInitData();
  }, [pagination?.current, pagination?.pageSize]);

  const showAssoModal = (type: string, row = { subTitle: '' }) => {
    const title = t(
      type === 'add' ? 'Model.addAssociations' : 'Model.checkAssociations'
    );
    const assorow = type === 'add' ? { src_model_id: modelId } : row;
    const subTitle = row.subTitle;
    assoRef.current?.showModal({
      title,
      type,
      assoInfo: assorow,
      subTitle,
    });
  };

  const showModelName = (id: string) => {
    return modelList.find((item) => item.model_id === id)?.model_name || '--';
  };

  const showDeleteConfirm = (id: string) => {
    confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await del(`/cmdb/api/model/association/${id}/`);
            message.success(t('successfullyDeleted'));
            if (pagination.current > 1 && tableData.length === 1) {
              pagination.current--;
            }
            fetchData();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const onSearchTxtChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const onTxtPressEnter = () => {
    pagination.current = 1;
    setPagination(pagination);
    fetchData();
  };

  const onTxtClear = () => {
    pagination.current = 1;
    setPagination(pagination);
    fetchData();
  };

  const handleTableChange = (pagination = {}) => {
    setPagination(pagination);
  };


  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await get(`/cmdb/api/model/${modelId}/association/`);
      setTableData(data);
    } finally {
      setLoading(false);
    }
  };

  const updateAssoList = () => {
    fetchData();
  };

  const getInitData = () => {
    const getAssoTypeList = get('/cmdb/api/model/model_association_type/');
    const getModelList = get('/cmdb/api/model/');
    const fetchAssoData = get(`/cmdb/api/model/${modelId}/association/`);
    const getCroupList = get('/cmdb/api/classification/');
    setLoading(true);
    Promise.all([getModelList, getAssoTypeList, fetchAssoData, getCroupList])
      .then((res) => {
        const modeldata: ModelItem[] = res[0];
        const assoTypeData: AssoTypeItem[] = res[1];
        const assoTableData: AssoTypeItem[] = res[2];
        const groupData: GroupItem[] = res[3];
        const _groups = deepClone(groupData).map((item: GroupItem) => ({
          ...item,
          list: [],
        }));
        modeldata.forEach((modelItem: ModelItem) => {
          const target = _groups.find(
            (item: GroupItem) =>
              item.classification_id === modelItem.classification_id
          );
          if (target) {
            target.list.push(modelItem);
          }
        });
        setGroups(_groups);
        setAssoTypeList(assoTypeData);
        setModelList(modeldata);
        setTableData(assoTableData);
        pagination.total = res[2].length || 0;
        setPagination(pagination);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  return (
    <div>
      <div>
        <div className="nav-box flex justify-end mb-[16px]">
          <div className="left-side w-[240px] mr-[8px]">
            <Input
              placeholder={t('search')}
              value={searchText}
              allowClear
              onChange={onSearchTxtChange}
              onPressEnter={onTxtPressEnter}
              onClear={onTxtClear}
            />
          </div>
          <div className="right-side">
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button
                type="primary"
                className="mr-[8px]"
                icon={<PlusOutlined />}
                onClick={() => showAssoModal('add')}
              >
                {t('common.addNew')}
              </Button>
            </PermissionWrapper>
          </div>
        </div>
        <CustomTable
          size="middle"
          scroll={{ y: 'calc(100vh - 340px)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={loading}
          rowKey="_id"
          onChange={handleTableChange}
        ></CustomTable>
      </div>
      <AssociationsModal
        ref={assoRef}
        constraintList={CONSTRAINT_List}
        allModelList={modelList}
        assoTypeList={assoTypeList}
        groups={groups}
        onSuccess={updateAssoList}
      />
    </div>
  );
};

export default Associations;
