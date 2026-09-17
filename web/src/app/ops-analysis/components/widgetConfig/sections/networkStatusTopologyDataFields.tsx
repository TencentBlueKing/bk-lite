import React from 'react';
import { Checkbox, Form, InputNumber } from 'antd';
import {
  NETWORK_STATUS_TOPOLOGY_MAX_NODE_LIMIT,
  networkStatusTopologySelectionExceedsLimit,
} from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { ConfigSectionTitle } from '../configTitles';
import type { NetworkSelectOption } from '../hooks/useNetworkStatusTopologyConfig';
import { NetworkStatusTopologyDeviceList } from './networkStatusTopologyDeviceList';
import { ThresholdColorListField } from './thresholdColorListField';

interface NetworkStatusTopologyDataFieldsProps {
  t: (key: string, defaultValue?: string) => string;
  nodeLimit?: number;
  listedOptions: NetworkSelectOption[];
  instanceTotal: number;
  instancePage: number;
  instancePageSize: number;
  instanceKeyword: string;
  instancesLoading: boolean;
  modelsLoading: boolean;
  modelFilter?: string;
  modelOptions: { label: string; value: string }[];
  onModelFilterChange: (value?: string) => void;
  onSearch: (keyword: string) => void;
  onPageChange: (page: number, pageSize: number) => void;
}

export const NetworkStatusTopologyDataFields: React.FC<
  NetworkStatusTopologyDataFieldsProps
> = ({
  t,
  nodeLimit,
  listedOptions,
  instanceTotal,
  instancePage,
  instancePageSize,
  instanceKeyword,
  instancesLoading,
  modelsLoading,
  modelFilter,
  modelOptions,
  onModelFilterChange,
  onSearch,
  onPageChange,
}) => {
  const form = Form.useFormInstance();

  return (
    <section>
      <ConfigSectionTitle>
        {t('dashboard.dataConfigSection', '数据配置')}
      </ConfigSectionTitle>
      <Form.Item
        label={t('dashboard.networkTopoDevices')}
        name={['networkStatusTopology', 'instUuids']}
        dependencies={[['networkStatusTopology', 'nodeLimit']]}
        rules={[
          { required: true, message: t('dashboard.networkTopoSelectDevicesRequired') },
          {
            validator: async (_, value) => {
              if (
                networkStatusTopologySelectionExceedsLimit(
                  value,
                  form.getFieldValue(['networkStatusTopology', 'nodeLimit']),
                )
              ) {
                throw new Error(t('dashboard.networkTopoSelectionExceedsLimit'));
              }
            },
          },
        ]}
        tooltip={t('dashboard.networkTopoDevicesHelp')}
      >
        <NetworkStatusTopologyDeviceList
          nodeLimit={nodeLimit}
          listedOptions={listedOptions}
          instanceTotal={instanceTotal}
          instancePage={instancePage}
          instancePageSize={instancePageSize}
          instanceKeyword={instanceKeyword}
          instancesLoading={instancesLoading}
          modelsLoading={modelsLoading}
          modelFilter={modelFilter}
          modelOptions={modelOptions}
          onModelFilterChange={onModelFilterChange}
          onSearch={onSearch}
          onPageChange={onPageChange}
        />
      </Form.Item>
      <Form.Item
        label={t('dashboard.networkTopoNodeLimit')}
        name={['networkStatusTopology', 'nodeLimit']}
        initialValue={100}
        tooltip={t('dashboard.networkTopoNodeLimitHelp')}
      >
        <InputNumber
          min={1}
          max={NETWORK_STATUS_TOPOLOGY_MAX_NODE_LIMIT}
          precision={0}
          className="w-full"
        />
      </Form.Item>
      <Form.Item
        label={t('dashboard.networkTopoLinkTraffic')}
        name={['networkStatusTopology', 'linkTrafficDisplays']}
        initialValue={['inbound', 'outbound']}
      >
        <Checkbox.Group
          options={[
            {
              label: t('dashboard.networkTopoLinkTrafficInbound'),
              value: 'inbound',
            },
            {
              label: t('dashboard.networkTopoLinkTrafficOutbound'),
              value: 'outbound',
            },
          ]}
        />
      </Form.Item>
      <Form.Item
        name={['networkStatusTopology', 'inboundTrafficThresholds']}
        noStyle
      >
        <ThresholdColorListField
          t={t}
          label={t('dashboard.networkTopoLinkTrafficInboundThresholds')}
          extra={t('dashboard.networkTopoTrafficThresholdHint')}
        />
      </Form.Item>
      <Form.Item
        name={['networkStatusTopology', 'outboundTrafficThresholds']}
        noStyle
      >
        <ThresholdColorListField
          t={t}
          label={t('dashboard.networkTopoLinkTrafficOutboundThresholds')}
          extra={t('dashboard.networkTopoTrafficThresholdHint')}
        />
      </Form.Item>
    </section>
  );
};
