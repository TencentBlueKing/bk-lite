import { useState, useCallback, useMemo } from 'react';
import { Collapse, Form } from 'antd';
import { useConfigRenderer } from './useConfigRenderer';
import { DataMapper } from './useDataMapper';
import {
  buildWebsiteRequestUrl,
  splitWebsiteRequestUrl,
  validateWebsiteRequestHeaders
} from './http-request-config';
import { applyMinioEditConfig, getMinioEditCompatibilityValues } from './minio-config';
import { resolveSnmpInterfaceFilterMode } from './snmpInterfaceFilterMode';
import useIntegrationApi from '@/app/monitor/api/integration';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { normalizePasswordFields } from '@/components/password/normalizePasswordWhitespace';

/**
 * 兜底：把 formFields 中非必填且用户未填的字段补齐。
 * 原因：前端表单只回填用户实际改过的字段，未改的 key 不会出现在 formData 里。
 * 但后端 Jinja2 模板（child.toml.j2）用 `{{ 字段名 }}` 渲染时，未定义的 key 会抛
 * UndefinedError,触发 "渲染采集模板失败"。
 *
 * 文本类可选字段补空串，配合模板 `{% if send %}{% endif %}` 跳过该行。
 * 布尔开关（或带 default_value 的字段）绝不能补空串：Jinja
 * `{{ x | default(false) }}` 对已定义的空串不会兜底，会渲出
 * `insecure_skip_verify = ` 这类非法 TOML，拖垮同机 Telegraf。
 *
 * 导出供单元测试使用。
 */
export const fillOptionalFormFields = (
  formData: Record<string, any>,
  formFields: any[] | undefined
): Record<string, any> => {
  if (!formFields?.length) return formData;
  const result = { ...formData };
  formFields.forEach((field: any) => {
    if (field.required === true) return;
    if (result[field.name] !== undefined) return;
    if (Object.prototype.hasOwnProperty.call(field, 'default_value')) {
      result[field.name] = field.default_value;
      return;
    }
    if (field.type === 'switch') {
      result[field.name] = false;
      return;
    }
    result[field.name] = '';
  });
  return result;
};

const WMI_USERNAME_HELP_MARKERS = [
  String.raw`domain\user`,
  String.raw`DOMAIN\monitor`,
  'WMI 查询账号',
  'WMI query account'
];

export const isWindowsWmiPluginConfig = (
  config: { config_type?: unknown } | null | undefined
) => {
  const types = config?.config_type;
  if (Array.isArray(types)) {
    return types.some((item) => String(item) === 'windows_wmi');
  }
  return String(types || '') === 'windows_wmi';
};

/**
 * 用户名帮助必须来自当前插件 UI.json，不能因为 name === "username"
 * 就套用 Windows WMI 的 domain\\user 文案。
 */
export const attachPluginOwnedFieldHelp = (
  field: any,
  config: { config_type?: unknown } | null | undefined
) => {
  if (!field || field.name !== 'username' || isWindowsWmiPluginConfig(config)) {
    return field;
  }
  const description = String(field.description || '');
  const placeholder = String(field.widget_props?.placeholder || '');
  const leaked = WMI_USERNAME_HELP_MARKERS.some(
    (marker) => description.includes(marker) || placeholder.includes(marker)
  );
  if (!leaked) {
    return field;
  }
  const nextWidgetProps = { ...(field.widget_props || {}) };
  if (WMI_USERNAME_HELP_MARKERS.some((marker) => placeholder.includes(marker))) {
    delete nextWidgetProps.placeholder;
  }
  return {
    ...field,
    description: WMI_USERNAME_HELP_MARKERS.some((marker) =>
      description.includes(marker)
    )
      ? undefined
      : field.description,
    widget_props: nextWidgetProps
  };
};

const INTERFACE_FILTER_FIELD_NAMES = new Set([
  'interface_filter_mode',
  'iftype_exclude',
  'iftype_include',
  'ifdescr_exclude',
  'ifdescr_include'
]);

interface FieldDependency {
  field?: string | string[];
  value?: unknown;
  conditions?: Array<Array<{ equals?: unknown }>>;
}

interface AdvancedFormField {
  name: string;
  section?: string;
  dependency?: FieldDependency;
}

/**
 * IF-MIB 的接口过滤只在接口表启用时才有意义。此处识别这一类独占高级面板，
 * 供外层直接随 enable_ifmib 隐藏整个折叠区，避免留下没有字段的空面板。
 */
export const isIfmibFilterAdvancedPanel = (advancedFields: AdvancedFormField[]) =>
  advancedFields.length > 0 &&
  advancedFields.every(
    (field) => {
      const dependency = field.dependency;
      const enableIfmibIndex = Array.isArray(dependency?.field)
        ? dependency.field.indexOf('enable_ifmib')
        : -1;
      const dependsOnEnabledIfmib =
        (dependency?.field === 'enable_ifmib' && dependency?.value === true) ||
        (enableIfmibIndex >= 0 && dependency?.conditions?.[enableIfmibIndex]?.some(
          (condition) => condition?.equals === true
        ));
      return (
        (field.section === 'interface_filter' || INTERFACE_FILTER_FIELD_NAMES.has(field.name)) &&
        dependsOnEnabledIfmib
      );
    }
  );

export const shouldRenderAdvancedFieldsPanel = (
  isIfmibFilterPanel: boolean,
  enableIfmib: unknown
) => !isIfmibFilterPanel || enableIfmib !== false;

export const usePluginFromJson = () => {
  const { isLoading } = useApiClient();
  const { t } = useTranslation();
  const [config, setConfig] = useState<any>(null);
  const [currentPluginId, setCurrentPluginId] = useState<
    string | number | null
  >(null);
  const { renderFormField, renderTableColumn } = useConfigRenderer();
  const { getUiTemplate, getUiTemplateByParams, getUiTemplateByPlugin } =
    useIntegrationApi();

  // 根据 pluginId 或参数获取配置
  const getPluginConfig = useCallback(
    async (
      pluginIdOrParams:
        | string
        | number
        | {
            collector: string;
            collect_type: string;
            monitor_object_id: string;
            monitor_plugin_id?: string | number;
          },
      mode?: 'edit'
    ) => {
      if (!pluginIdOrParams || isLoading) {
        return {};
      }
      try {
        let data;
        let pluginId;
        if (typeof pluginIdOrParams === 'object' && mode === 'edit') {
          if (pluginIdOrParams.monitor_plugin_id) {
            pluginId = pluginIdOrParams.monitor_plugin_id;
            data = await getUiTemplateByPlugin(pluginIdOrParams.monitor_plugin_id);
          } else {
            data = await getUiTemplateByParams(pluginIdOrParams);
            pluginId = `${pluginIdOrParams.monitor_object_id}_${pluginIdOrParams.collector}_${pluginIdOrParams.collect_type}`;
          }
        } else {
          pluginId = pluginIdOrParams as string | number;
          data = await getUiTemplate({ id: pluginId });
        }
        const resolvedConfig =
          data && typeof data === 'object' && 'ui_template' in data
            ? {
              ...(data.ui_template || {}),
              node_selector: data.node_selector || {},
              support_collect_detect: !!data.support_collect_detect
            }
            : data;
        if (resolvedConfig && Array.isArray(resolvedConfig.form_fields)) {
          resolvedConfig.form_fields = resolvedConfig.form_fields.map((field: any) =>
            attachPluginOwnedFieldHelp(field, resolvedConfig)
          );
        }
        setConfig(resolvedConfig);
        setCurrentPluginId(pluginId);
        return resolvedConfig;
      } catch {
        // 异常时返回默认配置
        const defaultConfig = {
          collect_type: '',
          config_type: [],
          collector: '',
          instance_type: '',
          object_name: '',
          form_fields: [],
          table_columns: []
        };
        setConfig(defaultConfig);
        const pluginId =
          typeof pluginIdOrParams === 'object'
            ? `${pluginIdOrParams.monitor_object_id}_${pluginIdOrParams.collector}_${pluginIdOrParams.collect_type}`
            : pluginIdOrParams;
        setCurrentPluginId(pluginId);
        return defaultConfig;
      }
    },
    [getUiTemplate, getUiTemplateByParams, getUiTemplateByPlugin, isLoading]
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
          getDefaultForm: () => ({})
        };
      }

      const getFieldsForMode = (fields: any[], mode: string) => {
        return fields
          ?.map((field: any) => {
            const fieldCopy = attachPluginOwnedFieldHelp({ ...field }, config);
            if (field.visible_in) {
              if (field.visible_in === 'auto' && mode === 'edit') return null;
              if (field.visible_in === 'edit' && mode === 'auto') return null;
            }
            if (
              mode === 'edit'
              && (field.editable === false || field.name === 'enable_ifmib')
            ) {
              fieldCopy.widget_props = {
                ...fieldCopy.widget_props,
                disabled: true
              };
            }
            return fieldCopy;
          })
          .filter(Boolean);
      };

      const formFields = getFieldsForMode(config.form_fields || [], extra.mode);
      const advancedFields = formFields?.filter((field: any) => field.advanced) || [];
      const basicFields = formFields?.filter((field: any) => !field.advanced) || [];
      const ADVANCED_SECTION_ORDER = ['request', 'auth', 'response', 'tls', 'interface_filter'];
      const advancedPanel = config.advanced_panel || {};
      const isInterfaceFilterAdvanced = isIfmibFilterAdvancedPanel(advancedFields);
      const advancedTitle =
        advancedPanel.title ||
        (isInterfaceFilterAdvanced
          ? t('monitor.integrations.advancedFilterConfiguration')
          : t('monitor.integrations.advancedConfiguration'));
      // 接口过滤只展示功能说明；互斥提示放在字段旁，避免顶部残留旧文案
      const advancedHint = isInterfaceFilterAdvanced
        ? t('monitor.integrations.advancedFilterConfigurationHint')
        : (advancedPanel.hint || t('monitor.integrations.advancedConfigurationHint'));

      const renderAdvancedFieldGroups = (fields: any[]) => {
        const hasSections = fields.some((field) => field.section);
        if (!hasSections) {
          return fields.map((fieldConfig: any) => renderFormField(fieldConfig, extra.mode));
        }

        const sectionMap = new Map<string, any[]>();
        fields.forEach((field) => {
          const section = field.section || 'other';
          if (!sectionMap.has(section)) sectionMap.set(section, []);
          sectionMap.get(section)!.push(field);
        });

        const orderedSections = [
          ...ADVANCED_SECTION_ORDER.filter((section) => sectionMap.has(section)),
          ...Array.from(sectionMap.keys()).filter(
            (section) => !ADVANCED_SECTION_ORDER.includes(section)
          ),
        ];

        return (
          <div className="space-y-5">
            {orderedSections.map((section) => (
              <section key={section} className="space-y-3">
                {/* 仅网站等多分组高级区展示小节标题；单一接口过滤组不再重复标题 */}
                {orderedSections.length > 1 && (
                  <div className="border-b border-[var(--color-border-1)] pb-2">
                    <h4 className="m-0 text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
                      {t(`monitor.integrations.advancedSections.${section}`)}
                    </h4>
                  </div>
                )}
                <div className="space-y-1">
                  {(sectionMap.get(section) || []).map((fieldConfig: any) =>
                    renderFormField(fieldConfig, extra.mode)
                  )}
                </div>
              </section>
            ))}
          </div>
        );
      };

      const formItems = (
        <>
          {basicFields.map((fieldConfig: any) =>
            renderFormField(fieldConfig, extra.mode)
          )}
          {advancedFields.length > 0 && (() => {
            // Ant Design：函数子节点的 Form.Item 必须带 truthy 的 shouldUpdate/dependencies，
            // 否则子节点不会渲染。网站拨测等非 IF-MIB 面板不能写 shouldUpdate={false}。
            const advancedCollapse = (
              <Collapse
                bordered={false}
                ghost
                className="mb-4 max-w-[720px] bg-transparent [&_.ant-collapse-header]:!items-center [&_.ant-collapse-header]:!px-0 [&_.ant-collapse-expand-icon]:!me-2 [&_.ant-collapse-content-box]:!px-0 [&_.ant-collapse-content-box]:!pb-1 [&_.ant-collapse-content-box]:!pt-3"
                expandIconPosition="start"
                items={[{
                  key: 'advanced-options',
                  label: (
                    <div>
                      <div className="text-[13px] font-medium leading-5 text-[var(--color-text-1)]">
                        {advancedTitle}
                      </div>
                      {advancedHint ? (
                        <div className="mt-0.5 text-[12px] font-normal leading-[18px] text-[var(--color-text-3)]">
                          {advancedHint}
                        </div>
                      ) : null}
                    </div>
                  ),
                  forceRender: true,
                  children: renderAdvancedFieldGroups(advancedFields),
                }]}
              />
            );
            if (!isInterfaceFilterAdvanced) {
              return advancedCollapse;
            }
            return (
              <Form.Item
                noStyle
                shouldUpdate={(previousValues, currentValues) =>
                  previousValues.enable_ifmib !== currentValues.enable_ifmib
                }
              >
                {({ getFieldValue }) =>
                  // 未初始化时沿用 enable_ifmib 默认 true；只有明确关闭才隐藏整个区域。
                  !shouldRenderAdvancedFieldsPanel(
                    isInterfaceFilterAdvanced,
                    getFieldValue('enable_ifmib')
                  )
                    ? null
                    : advancedCollapse
                }
              </Form.Item>
            );
          })()}
        </>
      );

      if (extra.mode === 'auto') {
        return {
          collect_type: config.collect_type,
          config_type: config.config_type,
          collector: config.collector,
          instance_type: config.instance_type,
          object_name: config.object_name,
          formItems,
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
            const normalizedRow = normalizePasswordFields(
              row,
              formFields,
              { includeReadOnly: true }
            ).values;
            const normalizedDataSource = (tableConfig.dataSource || []).map(
              (item: Record<string, unknown>) =>
                normalizePasswordFields(item, config.table_columns, {
                  includeReadOnly: true
                }).values
            );
            const filledRow = fillOptionalFormFields(normalizedRow, formFields);
            return DataMapper.transformAutoRequest(
              filledRow,
              normalizedDataSource,
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
                tableColumns: config.table_columns
              }
            );
          }
        };
      }

      if (extra.mode === 'edit') {
        return {
          collect_type: config.collect_type,
          config_type: config.config_type,
          collector: config.collector,
          instance_type: config.instance_type,
          object_name: config.object_name,
          formItems,
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
            // interface_filter_mode 不落库，需从 tagpass/tagdrop 反推，避免编辑回显恒为 exclude。
            if (formFields?.some((field: any) => field?.name === 'interface_filter_mode')) {
              formValues.interface_filter_mode = resolveSnmpInterfaceFilterMode(formValues);
            }
            if (config.instance_type === 'minio') {
              Object.assign(formValues, getMinioEditCompatibilityValues(apiData));
            }
            if (config.instance_type === 'web') {
              const requestUrl = apiData?.child?.content?.config?.urls?.[0];
              if (requestUrl) {
                const { baseUrl, entries } = splitWebsiteRequestUrl(requestUrl);
                formValues.monitor_url = baseUrl;
                formValues.request_params = entries;
              }
              const childConfig = apiData?.child?.content?.config || {};
              const authorization = childConfig.headers?.Authorization || childConfig.headers?.authorization;
              formValues.request_method = childConfig.method || 'GET';
              formValues.request_headers = Object.entries(childConfig.headers || {})
                .filter(([key]) => key.toLowerCase() !== 'authorization')
                .map(([key, value]) => ({ key, value: String(value ?? '') }));
              formValues.auth_type = authorization
                ? 'bearer'
                : childConfig.username
                  ? 'basic'
                  : 'none';
            }
            return formValues;
          },
          getParams: (formData: any, configForm: any) => {
            // 兼容两种格式：有 base 和没有 base
            const result: any = {
              ...configForm,
              child: {
                ...configForm.child,
                content: {
                  ...configForm.child.content,
                  config: {
                    ...configForm.child.content.config
                  }
                }
              }
            };
            // 如果有 base，也复制 base（保持结构）
            if (configForm.base) {
              result.base = {
                ...configForm.base,
                env_config: { ...configForm.base.env_config }
              };
            }
            // 把非必填字段未填的补成空串,避免后端 Jinja2 模板 {{ 字段名 }} 抛
            // UndefinedError；后端 child.toml.j2 用 {% if 字段 %}{% endif %} 跳过空串
            const filledFormData = { ...formData };
            formFields?.forEach((field: any) => {
              const { name, transform_on_edit, editable } = field;
              const formValue = filledFormData[name];
              // 跳过不可编辑的字段（只用于回显，不应写入）
              if (editable === false) {
                return;
              }
              if (formValue === undefined) {
                return;
              }
              if (transform_on_edit) {
                const transformedValue = DataMapper.transformValue(
                  formValue,
                  transform_on_edit,
                  'toApi',
                  undefined,
                  filledFormData
                );
                // 如果转换后的值是 undefined，跳过（表示该字段不需要写入）
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
                  // 解析路径中的变量（如 {{config_id}}）
                  targetPath = DataMapper.resolvePathVariables(
                    targetPath,
                    configForm
                  );
                  DataMapper.setNestedValue(
                    result,
                    targetPath,
                    transformedValue
                  );
                }
              }
            });
            // SNMP 接口黑白名单：空数组/空串不得写成 []（会误杀全部接口），改为删除对应键
            if (
              String(config.collect_type || '').startsWith('snmp') &&
              result?.child?.content?.config
            ) {
              const snmpFilterNames = new Set(
                (formFields || [])
                  .map((field: any) => field?.name)
                  .filter((name: string) =>
                    [
                      'iftype_include',
                      'iftype_exclude',
                      'ifdescr_include',
                      'ifdescr_exclude'
                    ].includes(name)
                  )
              );
              if (snmpFilterNames.size) {
                const snmpConfig = result.child.content.config;
                const pruneFilterKey = (
                  tableName: 'tagpass' | 'tagdrop',
                  key: string,
                  value: any
                ) => {
                  const empty =
                    value == null ||
                    value === '' ||
                    (Array.isArray(value) && value.length === 0);
                  if (!snmpConfig[tableName]) {
                    return;
                  }
                  if (empty) {
                    delete snmpConfig[tableName][key];
                    if (Object.keys(snmpConfig[tableName]).length === 0) {
                      delete snmpConfig[tableName];
                    }
                  }
                };
                if (snmpFilterNames.has('iftype_include')) {
                  pruneFilterKey(
                    'tagpass',
                    'ifType',
                    filledFormData.iftype_include
                  );
                }
                if (snmpFilterNames.has('iftype_exclude')) {
                  pruneFilterKey(
                    'tagdrop',
                    'ifType',
                    filledFormData.iftype_exclude
                  );
                }
                if (snmpFilterNames.has('ifdescr_include')) {
                  const descrInclude = DataMapper.transformValue(
                    filledFormData.ifdescr_include,
                    {
                      origin_path: 'child.content.config.tagpass.ifDescr',
                      to_api: { split: ',' }
                    },
                    'toApi',
                    undefined,
                    filledFormData
                  );
                  pruneFilterKey('tagpass', 'ifDescr', descrInclude);
                }
                if (snmpFilterNames.has('ifdescr_exclude')) {
                  const descrExclude = DataMapper.transformValue(
                    filledFormData.ifdescr_exclude,
                    {
                      origin_path: 'child.content.config.tagdrop.ifDescr',
                      to_api: { split: ',' }
                    },
                    'toApi',
                    undefined,
                    filledFormData
                  );
                  pruneFilterKey('tagdrop', 'ifDescr', descrExclude);
                }
                if (!snmpConfig.tagexclude) {
                  snmpConfig.tagexclude = ['ifType'];
                }
              }
            }
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
                      filledFormData
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
            if (config.instance_type === 'web') {
              const childConfig = result.child.content.config;
              const childEnvConfig = result.child.env_config || {};
              result.child.env_config = childEnvConfig;
              const childConfigId = String(result.child.id || '').toUpperCase();
              const passwordEnvKey = `PASSWORD__${childConfigId}`;
              const bearerEnvKey = `BEARER_TOKEN__${childConfigId}`;
              const setOptionalConfig = (key: string, value: any) => {
                if (value === undefined) return;
                if (value === null || value === '') {
                  delete childConfig[key];
                  return;
                }
                childConfig[key] = value;
              };
              result.child.content.config.urls = [
                buildWebsiteRequestUrl(
                  String(filledFormData.monitor_url || ''),
                  filledFormData.request_params || []
                )
              ];
              result.child.content.config.headers = Object.fromEntries(
                validateWebsiteRequestHeaders(filledFormData.request_headers || []).map(
                  ({ key, value }) => [key, value]
                )
              );
              childConfig.method = filledFormData.request_method || 'GET';
              if (childConfig.method !== 'POST') {
                delete childConfig.body;
              } else {
                setOptionalConfig('body', filledFormData.request_body);
              }
              setOptionalConfig('response_status_code', filledFormData.response_status_code);
              setOptionalConfig('response_string_match', filledFormData.response_string_match);
              setOptionalConfig(
                'response_timeout',
                filledFormData.response_timeout === undefined
                  ? undefined
                  : filledFormData.response_timeout === null || filledFormData.response_timeout === ''
                    ? ''
                    : `${filledFormData.response_timeout}s`
              );
              if (filledFormData.follow_redirects === undefined || filledFormData.follow_redirects === '') {
                delete childConfig.follow_redirects;
              } else {
                childConfig.follow_redirects = filledFormData.follow_redirects;
              }
              // 布尔开关：空串/缺省一律写成 false，避免 toml.dumps 产出
              // insecure_skip_verify = "" 拖垮同机 Telegraf。
              childConfig.insecure_skip_verify =
                filledFormData.insecure_skip_verify === true ||
                filledFormData.insecure_skip_verify === 'true';
              if (filledFormData.auth_type === 'basic') {
                delete result.child.content.config.bearer_token;
                delete result.child.content.config.headers.Authorization;
                delete result.child.content.config.headers.authorization;
                delete childEnvConfig[bearerEnvKey];
                result.child.content.config.password = `\${${passwordEnvKey}}`;
                if (filledFormData.ENV_PASSWORD !== undefined) {
                  childEnvConfig[passwordEnvKey] = filledFormData.ENV_PASSWORD;
                }
              } else if (filledFormData.auth_type === 'bearer') {
                delete result.child.content.config.username;
                delete result.child.content.config.password;
                result.child.content.config.headers.Authorization = `Bearer \${${bearerEnvKey}}`;
                delete childEnvConfig[passwordEnvKey];
                if (filledFormData.ENV_BEARER_TOKEN !== undefined) {
                  childEnvConfig[bearerEnvKey] = filledFormData.ENV_BEARER_TOKEN;
                }
              } else {
                delete result.child.content.config.username;
                delete result.child.content.config.password;
                delete result.child.content.config.bearer_token;
                delete result.child.content.config.headers.Authorization;
                delete result.child.content.config.headers.authorization;
                delete childEnvConfig[passwordEnvKey];
                delete childEnvConfig[bearerEnvKey];
              }
            }
            if (config.instance_type === 'minio') {
              applyMinioEditConfig(result, configForm, filledFormData);
            }
            // 如果有 base，统一同步 child.env_config 到 base.env_config
            if (result.base && result.child?.env_config) {
              Object.entries(result.child.env_config).forEach(
                ([key, value]) => {
                  // 移除 key 中的后缀（如 USER__8F39C34FEB234A52B9B43D4A846C10FF -> USER）
                  const baseEnvKey = key.split('__')[0];
                  result.base.env_config[baseEnvKey] = value;
                }
              );
            }
            return result;
          }
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
        getDefaultForm: () => ({})
      };
    },
    [config, currentPluginId, renderFormField, renderTableColumn, t]
  );

  return useMemo(
    () => ({
      buildPluginUI,
      getPluginConfig
    }),
    [buildPluginUI, getPluginConfig]
  );
};
