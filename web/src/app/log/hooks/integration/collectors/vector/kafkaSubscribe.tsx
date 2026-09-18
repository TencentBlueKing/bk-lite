import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useKafkaSubscribeVectorFormItems } from '../../common/kafkaSubscribeVectorFormItems';
import {
  buildKafkaSubscribeContent,
  getVectorKafkaSubscribeDefaultForm,
  getVectorKafkaSubscribeParams
} from './kafkaSubscribeDefaults';

export const useVectorConfig = () => {
  const commonFormItems = useKafkaSubscribeVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'kafka_subscribe',
    icon: 'mm-kafka_Kafka'
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const formItems = (
        <>
          {commonFormItems.getCommonFormItems({
            disabledFormItems: {}
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {
            topics: [],
            bootstrap_servers: [],
            group_id: '',
            auto_offset_reset: 'latest',
            sasl: {
              enabled: false,
              mechanism: 'PLAIN',
              username: '',
              password: ''
            },
            tls_enabled: false
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            const dataSource = config.dataSource || [];
            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [buildKafkaSubscribeContent(row)],
              instances: dataSource.map((item: TableDataItem) => {
                return {
                  ...item,
                  node_ids: [item.node_ids].flat()
                };
              })
            };
          }
        },
        edit: {
          formItems,
          getDefaultForm: getVectorKafkaSubscribeDefaultForm,
          getParams: getVectorKafkaSubscribeParams
        },
        manual: {
          defaultForm: {},
          formItems,
          getParams: (row: TableDataItem) => {
            return {
              instance_name: row.instance_name,
              instance_id: row.instance_id
            };
          },
          getConfigText: () => '--'
        }
      };
      return {
        ...pluginConfig,
        ...configs[extra.mode]
      };
    }
  };
};
