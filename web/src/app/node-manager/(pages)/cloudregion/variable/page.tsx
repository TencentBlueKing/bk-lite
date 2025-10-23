'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Button, Input, message } from 'antd';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import VariableModal from './variableModal';
import { ModalRef, TableDataItem, Pagination } from '@/app/node-manager/types';
import { useVarColumns } from '@/app/node-manager/hooks/variable';
import type { GetProps } from 'antd';
import MainLayout from '../mainlayout/layout';
import { PlusOutlined } from '@ant-design/icons';
import useNodeManagerApi from '@/app/node-manager/api';
import useApiClient from '@/utils/request';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import variableStyle from './index.module.scss';
import PermissionWrapper from '@/components/permission';
type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;

const Variable = () => {
  const cloudId = useCloudId();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getVariableList, deleteVariable } = useNodeManagerApi();
  const variableRef = useRef<ModalRef>(null);
  const [data, setData] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchText, setSearchText] = useState<string>('');
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  useEffect(() => {
    if (!isLoading) {
      getTablelist();
    }
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading) getTablelist(searchText);
  }, [pagination.current, pagination.pageSize]);

  const openUerModal = (type: string, form: TableDataItem) => {
    variableRef.current?.showModal({
      type,
      form,
    });
  };

  //遍历数据，取出要回显的数据
  const getFormDataById = (key: string) => {
    return data.find((item) => item.key === key) || {};
  };

  const delConfirm = (key: string) => {
    setLoading(true);
    deleteVariable(key)
      .then(() => {
        message.success(t('common.delSuccess'));
        getTablelist();
      })
      .catch(() => {
        setLoading(false);
      });
  };

  const columns = useVarColumns({
    openUerModal,
    getFormDataById,
    delConfirm,
  });

  const onSearch: SearchProps['onSearch'] = (value) => {
    setSearchText(value);
    getTablelist(value);
  };

  //获取表格数据
  const getTablelist = async (search = searchText) => {
    setLoading(true);
    try {
      const param = {
        cloud_region_id: cloudId,
        search,
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      const res = await getVariableList(param);
      const tempdata = res.items.map((item: any) => {
        return {
          ...item,
          key: item.id,
          name: item.key,
        };
      });
      setPagination((prev: Pagination) => ({
        ...prev,
        total: res?.count || 0,
      }));
      setData(tempdata);
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  return (
    <MainLayout>
      <div className={`${variableStyle.variable} w-full h-full`}>
        <div className="flex justify-end mb-4">
          <Search
            className="w-64 mr-[8px]"
            placeholder={t('common.search')}
            enterButton
            onSearch={onSearch}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type="primary"
              onClick={() => {
                openUerModal('add', {
                  name: '',
                  key: '',
                  value: '',
                  type: 'str',
                  description: '',
                });
              }}
            >
              <PlusOutlined />
              {t('common.add')}
            </Button>
          </PermissionWrapper>
        </div>
        <div className="tablewidth">
          <CustomTable
            scroll={{ y: 'calc(100vh - 376px)', x: 'calc(100vw - 300px)' }}
            loading={loading}
            columns={columns}
            dataSource={data}
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
        <VariableModal
          ref={variableRef}
          onSuccess={() => getTablelist()}
        ></VariableModal>
      </div>
    </MainLayout>
  );
};
export default Variable;
