'use client';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Input, Button, message, Dropdown, Space, Modal } from 'antd';
import type { GetProps, TableProps } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { ColumnFilterItem } from 'antd/es/table/interface';
import { useRouter, useSearchParams } from 'next/navigation';
import CustomTable from '@/components/custom-table';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import type {
  ConfigListProps,
  ConfigDate,
  SubRef,
} from '@/app/node-manager/types/cloudregion';
import useApiCloudRegion from '@/app/node-manager/api/cloudRegion';
import useApiCollector from '@/app/node-manager/api/collector';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import MainLayout from '../mainlayout/layout';
import configStyle from './index.module.scss';
import SubConfiguration from './subconfiguration';
import {
  useConfigColumns,
  useConfigBtachItems,
} from '@/app/node-manager/hooks/configuration';
import ConfigModal from './configModal';
import ApplyModal from './applyModal';
import PermissionWrapper from '@/components/permission';
type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;
const { confirm } = Modal;

const Configration = () => {
  const subConfiguration = useRef<SubRef>(null);
  const configurationRef = useRef<ModalRef>(null);
  const applyRef = useRef<ModalRef>(null);
  const cloudId = useCloudId();
  const router = useRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const nodeId = JSON.parse(
    sessionStorage.getItem('cloudRegionInfo') || '{}'
  ).id;
  const cloudregionId = searchParams.get('cloud_region_id') || '';
  const name = searchParams.get('name') || '';
  const { getConfiglist, getNodeList, batchDeleteCollector } =
    useApiCloudRegion();
  const { getCollectorlist } = useApiCollector();
  const configBtachItems = useConfigBtachItems();
  const [loading, setLoading] = useState<boolean>(true);
  const [configData, setConfigData] = useState<ConfigDate[]>([]);
  const [showSub, setShowSub] = useState<boolean>(false);
  const [filters, setFilters] = useState<ColumnFilterItem[]>([]);
  const [nodeData, setNodeData] = useState<ConfigDate>({
    key: '',
    name: '',
    collector_id: '',
    operatingSystem: '',
    nodeCount: 0,
    configInfo: '',
    nodes: [],
  });
  const [collectorIds, setCollectorIds] = useState<string[]>([]);
  const [originNodes, setOriginNodes] = useState<TableDataItem[]>([]);
  const [originConfigs, setOriginConfigs] = useState<ConfigListProps[]>([]);
  const [originCollectors, setOriginCollectors] = useState<TableDataItem[]>([]);
  const [selectedConfigurationRowKeys, setSelectedConfigurationRowKeys] =
    useState<React.Key[]>([]);

  useEffect(() => {
    if (isLoading) return;
    initPage();
    return () => {
      sessionStorage.removeItem('cloudRegionInfo');
    };
  }, [isLoading]);

  const showConfigurationModal = (type: string, form: any) => {
    configurationRef.current?.showModal({
      type,
      form,
    });
  };

  const showApplyModal = (form: TableDataItem) => {
    applyRef.current?.showModal({
      type: 'apply',
      form,
    });
  };

  const handleMenuClick = () => {
    confirm({
      title: t('common.prompt'),
      content: t('node-manager.cloudregion.variable.deleteinfo'),
      centered: true,
      onOk() {
        modifyDeleteconfirm();
      },
    });
  };

  const ConfigBtachProps = {
    items: configBtachItems,
    onClick: handleMenuClick,
  };

  //点击编辑配置文件的触发事件
  const configurationClick = (key: string) => {
    const configurationformdata = configData.find((item) => item.key === key);
    showConfigurationModal('edit', configurationformdata);
  };

  // 子配置编辑触发弹窗事件
  const hanldeSubEditClick = (item: any) => {
    showConfigurationModal('edit_child', item);
  };

  const openSub = (key: string, item?: any) => {
    if (item) {
      setNodeData({
        ...item,
        nodesList: originNodes.map((item) => ({
          label: item?.ip,
          value: item?.id,
        })),
      });
    }
    setShowSub(true);
  };

  const nodeClick = () => {
    router.push(
      `/node-manager/cloudregion/node?cloudregion_id=${cloudregionId}&name=${name}`
    );
  };

  //批量删除的确定的弹窗
  const modifyDeleteconfirm = async (id?: string) => {
    setLoading(true);
    const ids = id ? [id] : selectedConfigurationRowKeys;
    await batchDeleteCollector({
      ids: ids as string[],
    });
    if (!id) {
      setSelectedConfigurationRowKeys([]);
    }
    message.success(t('common.deleteSuccess'));
    getConfigData();
  };

  const applyConfigurationClick = (row: TableDataItem) => {
    showApplyModal(row);
  };

  const { columns } = useConfigColumns({
    configurationClick,
    filter: filters,
    openSub,
    nodeClick,
    modifyDeleteconfirm,
    applyConfigurationClick,
  });

  const tableData = useMemo(() => {
    if (!collectorIds.length) return configData;
    if (configData.length && collectorIds.length) {
      return configData.filter((item) => {
        return collectorIds.includes(item.collector_id as string);
      });
    }
    return [];
  }, [collectorIds, configData]);

  //获取配置文件列表
  const initPage = async () => {
    setLoading(true);
    try {
      const res = await Promise.all([
        getConfiglist({
          cloud_region_id: cloudId,
          node_id: nodeId || '',
        }),
        getNodeList({ cloud_region_id: cloudId }),
        getCollectorlist({}),
      ]);
      const configlist = res[0] || [];
      const nodeList = res[1] || [];
      const collectorList = res[2] || [];
      setFilterConfig(collectorList);
      setOriginConfigs(configlist);
      setOriginNodes(nodeList);
      dealConfigData({
        configlist,
        nodeList,
        collectorList,
      });
    } finally {
      setLoading(false);
    }
  };

  const dealConfigData = (
    config = {
      configlist: originConfigs,
      nodeList: originNodes,
      collectorList: originCollectors,
    }
  ) => {
    const nodes = config.nodeList.map((item) => ({
      label: item?.ip,
      value: item?.id,
    }));
    const data: any = config.configlist.map((item: ConfigListProps) => {
      return {
        ...item,
        key: item.id,
        operatingSystem: item.operating_system,
        configInfo: item.config_template,
        nodesList: nodes || [],
        collector_name: config.collectorList.find(
          (tex) => tex.id === item.collector_id
        )?.name,
      };
    });
    setConfigData(data);
  };

  const getConfigData = async (search = '') => {
    setLoading(true);
    try {
      const data = await getConfiglist({
        cloud_region_id: cloudId,
        node_id: nodeId || '',
        name: search,
      });
      dealConfigData({
        configlist: data,
        nodeList: originNodes,
        collectorList: originCollectors,
      });
    } finally {
      setLoading(false);
    }
  };

  // 根据采集器列表过滤数据
  const setFilterConfig = (data: TableDataItem[]) => {
    const collectors = data.filter((item: any) => !item.controller_default_run);
    setOriginCollectors(collectors);
    const filters = new Map();
    const collectorIds = collectors.map((item: any) => {
      filters.set(item.name, { text: item.name, value: item.name });
      return item.id;
    });
    setFilters(Array.from(filters.values()) as ColumnFilterItem[]);
    setCollectorIds(collectorIds);
  };

  //搜索框的触发事件
  const onSearch: SearchProps['onSearch'] = (value) => {
    getConfigData(value);
  };

  // 子配置返回配置页面事件
  const handleCBack = () => {
    getConfigData();
    setShowSub(false);
  };

  // 弹窗确认成功后的回调
  const onSuccess = () => {
    if (!showSub) {
      getConfigData();
      return;
    }
    subConfiguration.current?.getChildConfig();
  };

  //处理多选触发的事件逻辑
  const rowSelection: TableProps<TableProps>['rowSelection'] = {
    onChange: (selectedRowKeys: React.Key[]) => {
      setSelectedConfigurationRowKeys(selectedRowKeys);
    },
    //禁止选中
    getCheckboxProps: (record: any) => {
      return {
        disabled: !!record.nodes?.length,
      };
    },
  };

  return (
    <MainLayout>
      <div className={`${configStyle.config} w-full h-full`}>
        {!showSub ? (
          <>
            <div className="flex justify-end mb-4">
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button
                  className="mr-[8px]"
                  type="primary"
                  onClick={() => showConfigurationModal('add', {})}
                >
                  + {t('common.add')}
                </Button>
              </PermissionWrapper>
              <Dropdown
                className="mr-[8px]"
                overlayClassName="customMenu"
                menu={ConfigBtachProps}
                disabled={!selectedConfigurationRowKeys.length}
              >
                <Button>
                  <Space>
                    {t('common.bulkOperation')}
                    <DownOutlined />
                  </Space>
                </Button>
              </Dropdown>
              <Search
                className="w-64 mr-[8px]"
                placeholder={t('common.search')}
                enterButton
                onSearch={onSearch}
              />
            </div>
            <div className="tablewidth">
              <CustomTable<any>
                scroll={{ y: 'calc(100vh - 326px)', x: 'calc(100vw - 300px)' }}
                loading={loading}
                columns={columns}
                dataSource={tableData}
                rowSelection={rowSelection}
              />
            </div>
          </>
        ) : (
          <SubConfiguration
            ref={subConfiguration}
            collectors={originCollectors}
            cancel={() => handleCBack()}
            edit={hanldeSubEditClick}
            nodeData={nodeData}
          />
        )}
        {/* 弹窗组件（添加，编辑，应用）用于刷新页面 */}
        <ConfigModal
          ref={configurationRef}
          config={{ collectors: originCollectors }}
          onSuccess={onSuccess}
        ></ConfigModal>
        <ApplyModal
          ref={applyRef}
          config={{ nodes: originNodes }}
          onSuccess={() => getConfigData()}
        />
      </div>
    </MainLayout>
  );
};

export default Configration;
