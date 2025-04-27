'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Button, Input, message } from 'antd';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import VariableModal from './variableModal';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { useVarColumns } from '@/app/node-manager/hooks/variable';
import type { GetProps } from 'antd';
import Mainlayout from '../mainlayout/layout';
import { PlusOutlined } from '@ant-design/icons';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
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
  const { getvariablelist, deletevariable } = useApiCloudRegion();
  const variableRef = useRef<ModalRef>(null);
  const [data, setData] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!isLoading) {
      getVariablelist();
    }
  }, [isLoading]);

  const openUerModal = (type: string, form: TableDataItem) => {
    variableRef.current?.showModal({
      type,
      form,
    });
  };

  //遍历数据，取出要回显的数据
  const getFormDataById = (key: string) => {
    const formData = data.find((item) => item.key === key);
    if (!formData) {
      throw new Error(`Form data not found for key: ${key}`);
    }
    return formData;
  };

  const delconfirm = (key: string) => {
    deletevariable(key)
      .then(() => {
        message.success(t('common.delSuccess'));
      })
      .finally(() => {
        getVariablelist();
      });
  };

  const columns = useVarColumns({
    openUerModal,
    getFormDataById,
    delconfirm,
  });

  const onsuccessvariablemodal = () => {
    getVariablelist();
  };

  const onSearch: SearchProps['onSearch'] = (value) => {
    getvariablelist(cloudId, value).then((res) => {
      const tempdata = res.map((item: any) => {
        return {
          key: item.id,
          name: item.key,
          value: item.value,
          description: item.description,
        };
      });
      setData(tempdata);
    });
  };

  //获取表格数据
  const getVariablelist = () => {
    getvariablelist(cloudId)
      .then((res) => {
        setLoading(true);
        const tempdata = res.map((item: any) => {
          return {
            key: item.id,
            name: item.key,
            value: item.value,
            description: item.description,
          };
        });
        setData(tempdata);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  return (
    <Mainlayout>
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
            scroll={{ y: 'calc(100vh - 326px)', x: 'calc(100vw - 300px)' }}
            loading={loading}
            columns={columns}
            dataSource={data}
          />
        </div>
        <VariableModal
          ref={variableRef}
          onSuccess={onsuccessvariablemodal}
        ></VariableModal>
      </div>
    </Mainlayout>
  );
};
export default Variable;
