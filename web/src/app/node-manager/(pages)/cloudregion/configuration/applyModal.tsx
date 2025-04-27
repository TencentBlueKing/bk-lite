'use client';
import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Input, message, Button } from 'antd';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import {
  TableDataItem,
  ModalRef,
  ModalSuccess,
} from '@/app/node-manager/types/index';
import { useTranslation } from '@/utils/i18n';
import type { GetProps } from 'antd';
import { useApplyColumns } from '@/app/node-manager/hooks/configuration';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import {
  nodeItemtRes,
  mappedNodeItem,
} from '@/app/node-manager/types/cloudregion';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';

type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;

const ApplyModal = forwardRef<ModalRef, ModalSuccess>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const cloudId = useCloudId();
  const { getnodelist, applyconfig, cancelApply, getAssoNodes } =
    useApiCloudRegion();
  const [configVisible, setConfigVisible] = useState<boolean>(false);
  const [configForm, setConfigForm] = useState<TableDataItem>();
  const [applydata, setApplydata] = useState<mappedNodeItem[]>();
  const [type, setType] = useState<string>('apply');
  const [loading, setLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');

  //处理应用的事件
  const handleApply = async (row: TableDataItem) => {
    setLoading(true);
    const request = row.isRelated ? cancelApply : applyconfig;
    let params: any = {
      node_id: row.key,
      collector_configuration_id: configForm?.key,
    };
    if (!row.isRelated) {
      params = [params];
    }
    await request(params);
    message.success(t('common.operationSuccessful'));
    onSuccess();
    getApplydata({
      name: searchText,
      operating_system: configForm?.operating_system,
      id: configForm?.key,
    });
  };

  const applycolumns = useApplyColumns({ handleApply });

  useImperativeHandle(ref, () => ({
    showModal: ({ type, form }) => {
      // 开启弹窗的交互
      setConfigVisible(true);
      setType(type);
      setConfigForm(form);
      getApplydata({
        name: searchText,
        operating_system: form?.operating_system,
        id: form?.key,
      });
    },
  }));

  //关闭用户的弹窗(取消和确定事件)
  const handleCancel = () => {
    setConfigVisible(false);
    setLoading(false);
    setApplydata([]);
  };

  const onSearch: SearchProps['onSearch'] = (value) => {
    setSearchText(value);
    getApplydata({
      operating_system: configForm?.operating_system,
      name: value,
      id: configForm?.key,
    });
  };

  //获取应用列表的数据表格
  const getApplydata = async (params: TableDataItem) => {
    try {
      setLoading(true);
      const getNodeData = getnodelist({
        cloud_region_id: cloudId,
        name: params.name,
        operating_system: params.operating_system,
      });
      const getAssoConfig = getAssoNodes({
        cloud_region_id: cloudId,
        ids: [params.id as string],
      });
      Promise.all([getNodeData, getAssoConfig])
        .then((res) => {
          const data = (res[0] || []).map((item: nodeItemtRes) => {
            return {
              key: item.id,
              ip: item.ip,
              operatingsystem: item.operating_system,
              sidecar: !item.status.status ? 'Running' : 'Error',
              isRelated: !!(res[1][0]?.nodes || []).find(
                (tex: TableDataItem) => tex.id === item.id
              ),
            };
          });
          setApplydata(data);
        })
        .finally(() => {
          setLoading(false);
        });
    } catch {
      setLoading(false);
    }
  };

  return (
    <OperateModal
      title={t(`common.${type}`)}
      open={configVisible}
      onCancel={handleCancel}
      width={800}
      footer={
        <div>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <div className="w-full h-full overflow-hidden">
        <div className="sticky top-0 z-10">
          <Search
            className="w-64 mr-[8px] h-[40px]"
            placeholder="input search text"
            enterButton
            onSearch={onSearch}
          />
        </div>
        <div className="overflow-y-auto mt-2">
          <CustomTable
            columns={applycolumns}
            scroll={{ y: 'calc(100vh - 30%)' }}
            dataSource={applydata}
            loading={loading}
          />
        </div>
      </div>
    </OperateModal>
  );
});

ApplyModal.displayName = 'applyModal';
export default ApplyModal;
