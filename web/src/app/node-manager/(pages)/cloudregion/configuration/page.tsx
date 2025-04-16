'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Input } from 'antd';
import type { GetProps } from 'antd';
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
import useApiCollector from '@/app/node-manager/api/collector';
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
  const { getconfiglist, getnodelist } = useApiCloudRegion();
  const { getCollectorlist } = useApiCollector();
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
    nodeClick: (key: string) => {
      console.log(key)
    }
  });

  useEffect(() => {
    if (isLoading) return;
    getConfiglist(nodeId || '');
    getCollectorList();
  }, [isLoading]);

  //获取配置文件列表
  const getConfiglist = async (search?: string) => {
    setLoading(true);
    const res = await Promise.all([getconfiglist(Number(cloudid), search), getnodelist({cloud_region_id: Number(cloudid)})]);
    const configlist = res[0];
    const nodeList = res[1];
    const data = configlist.map((item: IConfiglistprops) => {
      const nodes = item.nodes?.map((node:string) => {
        const nodeItem = nodeList.find((nodeData: any) => nodeData.id === node);
        return nodeItem?.ip;
      });
      const config = {
        key: item.id,
        name: item.name,
        collector: item.collector as string,
        operatingsystem: item.operating_system,
        nodecount: item.node_count,
        configinfo: item.config_template,
        nodes: nodes?.length ? [...nodes,'1.1.1.1'] : '--',
      };
      return config;
    });
    setConfigdata(data);
    setLoading(false);
  };

  // 获取采集器列表
  const getCollectorList = async () => {
    const res = await getCollectorlist({});
    const filters = res.map((item: any) => item.id);
    setFilters(filters);
  }

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
  };

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
