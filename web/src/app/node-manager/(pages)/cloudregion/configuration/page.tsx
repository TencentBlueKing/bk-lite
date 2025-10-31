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
  ConfigData,
} from '@/app/node-manager/types/cloudregion';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { SafeStorage } from '@/app/node-manager/utils/safeStorage';
import MainLayout from '../mainlayout/layout';
import configStyle from './index.module.scss';
import SubConfigDrawer from './subConfigDrawer';
import {
  useConfigColumns,
  useConfigBtachItems,
} from '@/app/node-manager/hooks/configuration';
import ConfigModal from './configModal';
import ApplyModal from './applyModal';
import PermissionWrapper from '@/components/permission';
import { ListItem } from '@/types';

type SearchProps = GetProps<typeof Input.Search>;
const { Search } = Input;
const { confirm } = Modal;

const Configuration = () => {
  const subConfigDrawer = useRef<any>(null);
  const configurationRef = useRef<ModalRef>(null);
  const applyRef = useRef<ModalRef>(null);
  const cloudId = useCloudId();
  const router = useRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const nodeId = SafeStorage.getSessionItem<{ id: string }>(
    'cloudRegionInfo'
  )?.id;
  const cloudregionId = searchParams.get('cloud_region_id') || '';
  const name = searchParams.get('name') || '';
  const { getConfiglist, batchDeleteCollector, getNodeList, getCollectorlist } =
    useNodeManagerApi();
  const configBtachItems = useConfigBtachItems();
  const [loading, setLoading] = useState<boolean>(true);
  const [configData, setConfigData] = useState<ConfigData[]>([]);
  const [filters, setFilters] = useState<ColumnFilterItem[]>([]);
  const [collectorIds, setCollectorIds] = useState<string[]>([]);
  const [originNodes, setOriginNodes] = useState<TableDataItem[]>([]);
  const [originCollectors, setOriginCollectors] = useState<TableDataItem[]>([]);
  const [selectedConfigurationRowKeys, setSelectedConfigurationRowKeys] =
    useState<React.Key[]>([]);

  useEffect(() => {
    if (isLoading) return;
    initPage();
    return () => {
      SafeStorage.removeSessionItem('cloudRegionInfo');
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

  const openSub = (key: string, item?: any) => {
    if (item) {
      const nodeData = {
        ...item,
        nodesList: originNodes.map((item) => ({
          label: item?.ip,
          value: item?.id,
        })),
      };
      subConfigDrawer.current?.showModal({
        title: t('node-manager.cloudregion.Configuration.subconfiguration'),
        form: nodeData,
      });
    }
  };

  const nodeClick = () => {
    router.push(
      `/node-manager/cloudregion/node?cloudregion_id=${cloudregionId}&name=${name}`
    );
  };

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
    filter: filters,
    openSub,
    nodeClick,
    modifyDeleteconfirm,
    applyConfigurationClick,
  });

  const tableData = useMemo(() => {
    if (!collectorIds.length) {
      return configData;
    }

    if (configData.length && collectorIds.length) {
      return configData.filter((item) => {
        return collectorIds.includes(item.collector_id as string);
      });
    }
    return [];
  }, [collectorIds, configData]);

  const initPage = async () => {
    setLoading(true);
    try {
      let res;
      try {
        res = await Promise.all([
          getConfiglist({
            cloud_region_id: cloudId,
            node_id: nodeId || '',
          }),
          getNodeList({ cloud_region_id: cloudId }),
          getCollectorlist({}),
        ]);
      } catch {
        res = [[], [], []];
      }

      const [configlist, nodeList, collectorList] = res;

      setFilterConfig(collectorList);
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

  const dealConfigData = (config: {
    configlist: ConfigListProps[];
    nodeList: TableDataItem[];
    collectorList: TableDataItem[];
  }) => {
    const nodes = config.nodeList.map((item) => ({
      label: item?.ip,
      value: item?.id,
    }));
    const data = config.configlist.map(
      (item: ConfigListProps): ConfigData => ({
        ...item,
        key: item.id,
        operatingSystem: item.operating_system,
        configInfo: item.config_template || '',
        nodesList: nodes as ListItem,
        nodeCount: item.nodes?.length || 0,
        collector_name:
          config.collectorList.find(
            (collector) => collector.id === item.collector_id
          )?.name || '',
      })
    );

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
        configlist: data || [],
        nodeList: originNodes,
        collectorList: originCollectors,
      });
    } catch (error) {
      console.error('Failed to fetch config data:', error);
      setConfigData([]);
    } finally {
      setLoading(false);
    }
  };

  const setFilterConfig = (data: TableDataItem[]) => {
    const collectors = data.filter((item: any) => !item.controller_default_run);
    setOriginCollectors(collectors);
    const filtersMap = new Map();
    const collectorIds = collectors.map((item: any) => {
      filtersMap.set(item.name, { text: item.name, value: item.name });
      return item.id;
    });
    setFilters(Array.from(filtersMap.values()) as ColumnFilterItem[]);
    setCollectorIds(collectorIds);
  };

  const onSearch: SearchProps['onSearch'] = (value) => {
    getConfigData(value);
  };

  const onSuccess = () => {
    getConfigData();
  };

  const rowSelection: TableProps<TableProps>['rowSelection'] = {
    onChange: (selectedRowKeys: React.Key[]) => {
      setSelectedConfigurationRowKeys(selectedRowKeys);
    },
    getCheckboxProps: (record: any) => {
      return {
        disabled: !!record.nodes?.length,
      };
    },
  };

  return (
    <MainLayout>
      <div className={`${configStyle.config} w-full h-full`}>
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

        <ConfigModal
          ref={configurationRef}
          config={{ collectors: originCollectors }}
          onSuccess={onSuccess}
        />
        <ApplyModal
          ref={applyRef}
          config={{ nodes: originNodes }}
          onSuccess={() => getConfigData()}
        />

        <SubConfigDrawer
          ref={subConfigDrawer}
          collectors={originCollectors}
          onSuccess={onSuccess}
        />
      </div>
    </MainLayout>
  );
};

export default Configuration;
