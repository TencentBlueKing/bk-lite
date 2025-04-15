'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Input } from 'antd';
import type { TableProps, GetProps } from 'antd';
import { useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import { ModalRef } from '@/app/node-manager/types/index';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import type {
  IConfiglistprops,
  ConfigDate,
  SubRef,
} from '@/app/node-manager/types/cloudregion';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import useCloudId from '@/app/node-manager/hooks/useCloudid';
import Mainlayout from '../mainlayout/layout';
import configstyle from './index.module.scss';
import SubConfiguration from './subconfiguration';
import { useConfigColumns } from '@/app/node-manager/hooks/configuration';
import ConfigModal from './configModal';
type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;

const Configration = () => {
  const subConfiguration = useRef<SubRef>(null);
  const configurationRef = useRef<ModalRef>(null);
  const cloudid = useCloudId();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const nodeId = searchParams.get('id') || '';
  const { getconfiglist } = useApiCloudRegion();
  const [selectedconfigurationRowKeys, setSelectedconfigurationRowKeys] =
    useState<React.Key[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [configdata, setConfigdata] = useState<ConfigDate[]>([]);
  const [showSub, setShowSub] = useState<boolean>(false);
  const [filters, setFilters] = useState<string[]>([]);
  const [nodeData, setNodeData] = useState<ConfigDate>({
    key: '',
    name: '',
    collector: '',
    operatingsystem: '',
    nodecount: 0,
    configinfo: '',
    nodes: [],
  });

  const showConfigurationModal = (type:string, form: any) => {
    configurationRef.current?.showModal({
      type,
      form,
    })
  }

  //点击编辑配置文件的触发事件
  const configurationClick = (key: string) => {
    const configurationformdata = configdata.find((item) => item.key === key);
    showConfigurationModal('edit', configurationformdata);
  };

  // 子配置编辑触发弹窗事件
  const hanldeSubEditClick = (item: any) => {
    showConfigurationModal('edit_child', item);
  };

  const openSub = (key: string, item?: any) => {
    setNodeData(item);
    setShowSub(true);
  };

  const { columns } = useConfigColumns({
    configurationClick,
    filter: filters as string[],
    openSub,
  });

  useEffect(() => {
    if (isLoading) return;
    getConfiglist(nodeId || '');
  }, [isLoading]);

  //处理多选触发的事件逻辑
  const rowSelection: TableProps<TableProps>['rowSelection'] = {
    onChange: (selectedRowKeys: React.Key[]) => {
      console.log(selectedconfigurationRowKeys);
      setSelectedconfigurationRowKeys(selectedRowKeys);
    },
    //禁止选中
    getCheckboxProps: (record: any) => {
      return {
        disabled: record.nodecount,
        name: record.name,
      };
    },
  };

  //获取配置文件列表
  const getConfiglist = (search?: string) => {
    setLoading(true);
    getconfiglist(Number(cloudid), search)
      .then((res) => {
        const filterSet = new Set<string>();
        const data = res.map((item: IConfiglistprops) => {
          const config = {
            key: item.id,
            name: item.name,
            collector: item.collector as string,
            operatingsystem: item.operating_system,
            nodecount: item.node_count,
            configinfo: item.config_template,
            nodes: item.nodes?.length ? item.nodes[0] : '--',
          };
          filterSet.add(item.collector as string);
          return config;
        });
        setFilters(Array.from(filterSet));
        setConfigdata(data);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  //搜索框的触发事件
  const onSearch: SearchProps['onSearch'] = (value) => {
    getConfiglist(value);
  };

  // 子配置返回配置页面事件
  const handleCBack = () => {
    getConfiglist();
    setShowSub(false);
  };

  // 弹窗确认成功后的回调
  const onSuccess = () => {
    if (!showSub) {
      getConfiglist();
      return;
    }
    subConfiguration.current?.getChildConfig();
  }

  return (
    <Mainlayout>
      <div className={`${configstyle.config} w-full h-full`}>
        {!showSub ? (
          <>
            <div className="flex justify-end mb-4">
              <Search
                className="w-64 mr-[8px]"
                placeholder={t('common.search')}
                enterButton
                onSearch={onSearch}
              />
            </div>
            <div className="tablewidth">
              <CustomTable<any>
                loading={loading}
                scroll={{ y: 'calc(100vh - 400px)', x: 'max-content' }}
                columns={columns}
                dataSource={configdata}
                rowSelection={rowSelection}
              />
            </div>
          </>
        ) : (
          <SubConfiguration
            ref={subConfiguration}
            cancel={() => handleCBack()}
            edit={hanldeSubEditClick}
            nodeData={nodeData}
          />
        )}
        {/* 弹窗组件（添加，编辑，应用）用于刷新页面 */}
        <ConfigModal
          ref={configurationRef}
          onSuccess={onSuccess}
        ></ConfigModal>
      </div>
    </Mainlayout>
  );
};

export default Configration;
