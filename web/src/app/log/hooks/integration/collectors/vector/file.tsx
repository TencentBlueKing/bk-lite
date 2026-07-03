import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFileVectorFormItems } from '../../common/fileVectorFormItems';
import {
  getVectorFileDefaultForm,
  getVectorFileParams
} from './fileDefaults';

export const useVectorConfig = () => {
  const commonFormItems = useFileVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'file',
    icon: 'll-file_文件采集'
  };

  return {
    getConfig: (extra: {
      dataSource?: IntegrationLogInstance[];
      mode: 'manual' | 'auto' | 'edit';
      onTableDataChange?: (data: IntegrationLogInstance[]) => void;
    }) => {
      const disabledForm = {
        include: false
      };
      const formItems = (
        <>
          {commonFormItems.getCommonFormItems({
            disabledFormItems: disabledForm
          })}
        </>
      );
      const configs = {
        auto: {
          formItems: commonFormItems.getCommonFormItems(),
          initTableItems: {},
          defaultForm: {
            include: [],
            exclude: [],
            read_from: 'beginning',
            ignore_older_secs: 86400,
            encoding_charset: 'utf-8',
            parser_type: '',
            multiline: {
              enabled: false,
              mode: 'continue_through',
              start_pattern: '',
              timeout_ms: 1000,
              condition_pattern: ''
            }
          },
          columns: [],
          getParams: (row: IntegrationLogInstance, config: TableDataItem) => {
            // auto 模式保留旧实现：它构造的是一个数组项（configs: [content]），
            // 与 edit 模式的 child.content 结构不同，不复用 getVectorFileParams。
            const dataSource = config.dataSource || [];
            const formDataCopy = { ...row };

            const content: Record<string, unknown> = {
              include: formDataCopy.include || [],
              exclude: formDataCopy.exclude || [],
              read_from: formDataCopy.read_from,
              ignore_older_secs: formDataCopy.ignore_older_secs,
              encoding_charset: formDataCopy.encoding_charset
            };

            if (formDataCopy.parser_type) {
              content.parser_type = formDataCopy.parser_type;
            }

            if (formDataCopy.multiline?.enabled) {
              content.multiline = {
                condition_pattern: formDataCopy.multiline.condition_pattern,
                mode: formDataCopy.multiline.mode,
                start_pattern: formDataCopy.multiline.start_pattern,
                timeout_ms: formDataCopy.multiline.timeout_ms
              };
            }

            return {
              collector: pluginConfig.collector,
              collect_type: pluginConfig.collect_type,
              configs: [content],
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
          // 从 ./fileDefaults 导入的纯函数 —— 与 getVectorFileParams 写入结构一致
          getDefaultForm: getVectorFileDefaultForm,
          getParams: getVectorFileParams
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