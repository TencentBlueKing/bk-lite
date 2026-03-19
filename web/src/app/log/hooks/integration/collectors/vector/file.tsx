import React from 'react';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import { TableDataItem } from '@/app/log/types';
import { useFileVectorFormItems } from '../../common/fileVectorFormItems';
import { cloneDeep } from 'lodash';

export const useVectorConfig = () => {
  const commonFormItems = useFileVectorFormItems();
  const pluginConfig = {
    collector: 'Vector',
    collect_type: 'file',
    icon: 'jiaoxuerizhiPC'
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
            const dataSource = cloneDeep(config.dataSource || []);
            const formDataCopy = cloneDeep(row);

            // 构建 content
            const content: Record<string, unknown> = {
              include: formDataCopy.include || [],
              exclude: formDataCopy.exclude || [],
              read_from: formDataCopy.read_from,
              ignore_older_secs: formDataCopy.ignore_older_secs,
              encoding_charset: formDataCopy.encoding_charset
            };

            // 处理 parser_type
            if (formDataCopy.parser_type) {
              content.parser_type = formDataCopy.parser_type;
            }

            // 处理 multiline
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
          getDefaultForm: (formData: TableDataItem) => {
            const content = formData?.child?.content || {};

            // Vector 的数据结构: content.sources.file_xxx
            const sources = content.sources || {};
            const sourceKey =
              Object.keys(sources).find((key) => key.startsWith('file_')) || '';
            const sourceData = sources[sourceKey] || {};

            return {
              include: sourceData.include || [],
              exclude: sourceData.exclude || [],
              read_from: sourceData.read_from || 'beginning',
              ignore_older_secs: sourceData.ignore_older_secs || 86400,
              encoding_charset: sourceData.encoding_charset || 'utf-8',
              parser_type: sourceData.parser_type || '',
              multiline: {
                enabled: !!sourceData.multiline?.mode,
                mode: sourceData.multiline?.mode || 'continue_through',
                start_pattern: sourceData.multiline?.start_pattern || '',
                timeout_ms: sourceData.multiline?.timeout_ms || 1000,
                condition_pattern: sourceData.multiline?.condition_pattern || ''
              }
            };
          },
          getParams: (formData: TableDataItem, configForm: TableDataItem) => {
            const originalChild = cloneDeep(configForm?.child || {});
            const formDataCopy = cloneDeep(formData);

            // 构建 content 对象
            const content: Record<string, unknown> = {
              include: formDataCopy.include || [],
              exclude: formDataCopy.exclude || [],
              read_from: formDataCopy.read_from,
              ignore_older_secs: formDataCopy.ignore_older_secs,
              encoding_charset: formDataCopy.encoding_charset
            };

            // 处理 parser_type
            if (formDataCopy.parser_type) {
              content.parser_type = formDataCopy.parser_type;
            }

            // 处理 multiline
            if (formDataCopy.multiline?.enabled) {
              content.multiline = {
                condition_pattern: formDataCopy.multiline.condition_pattern,
                mode: formDataCopy.multiline.mode,
                start_pattern: formDataCopy.multiline.start_pattern,
                timeout_ms: formDataCopy.multiline.timeout_ms
              };
            }

            return {
              child: {
                ...originalChild,
                content
              }
            };
          }
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
