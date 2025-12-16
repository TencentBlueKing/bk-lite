import { useState, useCallback } from 'react';
import { useConfigRenderer } from './useConfigRenderer';
import { DataMapper } from './useDataMapper';
import useIntegrationApi from '@/app/monitor/api/integration';
import useApiClient from '@/utils/request';

export const usePluginFromJson = () => {
  const { isLoading } = useApiClient();
  const [config, setConfig] = useState<any>(null);
  const [currentPluginId, setCurrentPluginId] = useState<
    string | number | null
  >(null);
  const { renderFormField, renderTableColumn } = useConfigRenderer();
  const { getUiTemplate } = useIntegrationApi();

  // 根据 pluginId 获取配置
  const getPluginConfig = useCallback(
    async (pluginId: string | number) => {
      if (!pluginId || isLoading) {
        return {};
      }
      try {
        const data = await getUiTemplate({ id: pluginId });
        setConfig(data);
        setCurrentPluginId(pluginId);
        return data;
      } catch {
        // 异常时返回默认配置
        const defaultConfig = {
          collect_type: '',
          config_type: [],
          collector: '',
          instance_type: '',
          object_name: '',
          form_fields: [],
          table_columns: [],
        };
        setConfig(defaultConfig);
        setCurrentPluginId(pluginId);
        return defaultConfig;
      }
    },
    [isLoading]
  );

  const buildPluginUI = useCallback(
    (
      pluginId: string | number,
      extra: {
        dataSource?: any[];
        mode: 'manual' | 'auto' | 'edit';
        onTableDataChange?: (data: any[]) => void;
        form?: any;
        externalOptions?: Record<string, any[]>;
      }
    ) => {
      // 如果当前没有配置或 pluginId 不匹配，返回空配置
      if (!config || currentPluginId !== pluginId) {
        return {
          collect_type: '',
          config_type: [],
          collector: '',
          instance_type: '',
          object_name: '',
          formItems: null,
          columns: [],
          initTableItems: {},
          defaultForm: {},
          getParams: () => ({}),
          getDefaultForm: () => ({}),
        };
      }

      const getFieldsForMode = (fields: any[], mode: string) => {
        return fields
          ?.map((field: any) => {
            const fieldCopy = { ...field };
            if (field.visible_in) {
              if (field.visible_in === 'auto' && mode === 'edit') return null;
              if (field.visible_in === 'edit' && mode === 'auto') return null;
            }
            if (mode === 'edit' && field.editable === false) {
              fieldCopy.widget_props = {
                ...field.widget_props,
                disabled: true,
              };
            }
            return fieldCopy;
          })
          .filter(Boolean);
      };

      const formFields = getFieldsForMode(config.form_fields || [], extra.mode);

      if (extra.mode === 'auto') {
        return {
          collect_type: config.collect_type,
          config_type: config.config_type,
          collector: config.collector,
          instance_type: config.instance_type,
          object_name: config.object_name,
          formItems: (
            <>
              {formFields?.map((fieldConfig: any) =>
                renderFormField(fieldConfig)
              )}
            </>
          ),
          columns:
            config.table_columns?.map((columnConfig: any) =>
              renderTableColumn(
                columnConfig,
                extra.dataSource || [],
                extra.onTableDataChange || (() => {}),
                extra.externalOptions
              )
            ) || [],
          initTableItems:
            config.table_columns?.reduce((acc: any, column: any) => {
              acc[column.name] = column.default_value || null;
              return acc;
            }, {}) || {},
          defaultForm:
            formFields?.reduce((acc: any, field: any) => {
              if ('default_value' in field) {
                acc[field.name] = field.default_value;
              }
              return acc;
            }, {}) || {},
          getParams: (row: any, tableConfig: any) => {
            return DataMapper.transformAutoRequest(
              row,
              tableConfig.dataSource || [],
              {
                config_type: config.config_type,
                collect_type: config.collect_type,
                collector: config.collector,
                instance_type: config.instance_type,
                objectId: tableConfig.objectId,
                nodeList: tableConfig.nodeList,
                instance_id: config.instance_id,
                config_type_field: config.config_type_field,
                formFields: formFields,
                tableColumns: config.table_columns,
              }
            );
          },
        };
      }

      if (extra.mode === 'edit') {
        return {
          collect_type: config.collect_type,
          config_type: config.config_type,
          collector: config.collector,
          instance_type: config.instance_type,
          object_name: config.object_name,
          formItems: (
            <>
              {formFields?.map((fieldConfig: any) =>
                renderFormField(fieldConfig)
              )}
            </>
          ),
          getDefaultForm: (apiData: any) => {
            const formValues: any = {};
            formFields?.forEach((field: any) => {
              const { name, transform_on_edit } = field;
              if (transform_on_edit) {
                formValues[name] = DataMapper.transformValue(
                  null,
                  transform_on_edit,
                  'toForm',
                  apiData
                );
              }
            });
            return formValues;
          },
          getParams: (formData: any, configForm: any) => {
            const result = {
              ...configForm,
              child: {
                ...configForm.child,
                content: {
                  ...configForm.child.content,
                  config: {
                    ...configForm.child.content.config,
                  },
                },
              },
            };
            formFields?.forEach((field: any) => {
              const { name, transform_on_edit } = field;
              const formValue = formData[name];
              if (formValue === undefined) {
                return;
              }
              if (transform_on_edit) {
                const transformedValue = DataMapper.transformValue(
                  formValue,
                  transform_on_edit,
                  'toApi',
                  undefined,
                  formData
                );
                if (transformedValue === undefined) {
                  return;
                }
                // 获取目标路径
                let targetPath;
                if (typeof transform_on_edit === 'string') {
                  // 兼容旧格式：字符串直接作为路径
                  targetPath = transform_on_edit;
                } else {
                  // 优先使用 origin_path（完整路径），这是 edit 模式的标准方式
                  targetPath =
                    transform_on_edit.origin_path ||
                    transform_on_edit.originPath;
                }

                if (targetPath) {
                  DataMapper.setNestedValue(
                    result,
                    targetPath,
                    transformedValue
                  );
                }
              }
            });
            // 处理额外字段（extra_edit_fields）
            if (config.extra_edit_fields) {
              Object.entries(config.extra_edit_fields).forEach(
                ([fieldName, transformConfig]: [string, any]) => {
                  console.log(fieldName);
                  // transformConfig 直接是转换配置，不再有嵌套的 transform_on_edit
                  if (transformConfig) {
                    const transformedValue = DataMapper.transformValue(
                      null,
                      transformConfig,
                      'toApi',
                      undefined,
                      formData
                    );
                    const targetPath = transformConfig.origin_path;
                    if (targetPath && transformedValue !== undefined) {
                      DataMapper.setNestedValue(
                        result,
                        targetPath,
                        transformedValue
                      );
                    }
                  }
                }
              );
            }
            return result;
          },
        };
      }

      return {
        collect_type: config.collect_type || '',
        config_type: config.config_type || [],
        collector: config.collector || '',
        instance_type: config.instance_type || '',
        object_name: config.object_name || '',
        formItems: null,
        columns: [],
        initTableItems: {},
        defaultForm: {},
        getParams: () => ({}),
        getDefaultForm: () => ({}),
      };
    },
    [config, currentPluginId, renderFormField, renderTableColumn]
  );

  return {
    buildPluginUI,
    getPluginConfig,
  };
};
