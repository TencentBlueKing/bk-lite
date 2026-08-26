'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo
} from 'react';
import {
  Input,
  Button,
  Form,
  message,
  Select,
  Cascader,
  InputNumber,
  ColorPicker,
  Descriptions,
  Tag,
  theme,
  Popover,
  Spin,
  Empty
} from 'antd';
import { AggregationColor } from 'antd/es/color-picker/color';
import { PlusOutlined, MinusOutlined, CloseOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/monitor/context/common';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useApiClient, { HandledRequestError } from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { ModalRef, ListItem } from '@/app/monitor/types';
import { MetricInfo } from '@/app/monitor/types/integration';
import { DimensionItem, EnumItem } from '@/app/monitor/types/integration';
import { useTranslation } from '@/utils/i18n';
import type { ColorPickerProps } from 'antd';
import { generate, green, presetPalettes, red } from '@ant-design/colors';
import { findCascaderPath } from '@/app/monitor/utils/common';
import {
  ensureMetricLabelsPlaceholder,
  stripMetricLabelsPlaceholder
} from '@/app/monitor/utils/metricQueryLabels';
import { cloneDeep } from 'lodash';
const { Option } = Select;

interface ModalProps {
  onSuccess: () => void;
  groupList: ListItem[];
  monitorObject: number;
  pluginId: number;
}

type Presets = Required<ColorPickerProps>['presets'][number];
type DimensionMode = 'input' | 'select';
type FormulaTestStatus = 'idle' | 'passed' | 'failed';

const METRIC_FORMULA_ERROR_TOAST_KEY = 'monitor-metric-formula-error';

/** 报错 toast：文案与「查看详情」基线对齐；详情浮层贴着链接右侧弹出 */
const MetricQueryErrorToast = ({
  summary,
  detail,
  viewDetailLabel,
  detailTitle,
  closeLabel,
  onClose
}: {
  summary: string;
  detail?: string;
  viewDetailLabel: string;
  detailTitle: string;
  closeLabel: string;
  onClose: () => void;
}) => {
  const detailText = (detail || '').trim();
  const hasDetail = !!detailText && detailText !== summary.trim();

  return (
    <div
      role="alert"
      className="inline-flex w-fit max-w-[min(440px,72vw)] items-baseline gap-2 text-left"
    >
      <p className="m-0 min-w-0 whitespace-normal break-words text-sm leading-5 text-[var(--color-text-1)]">
        {summary}
      </p>
      {hasDetail ? (
        <Popover
          trigger={['hover', 'click']}
          placement="right"
          arrow={{ pointAtCenter: true }}
          mouseEnterDelay={0.08}
          mouseLeaveDelay={0.2}
          autoAdjustOverflow
          destroyOnHidden
          getPopupContainer={() => document.body}
          zIndex={3000}
          styles={{
            body: {
              padding: 0,
              borderRadius: 8,
              overflow: 'hidden'
            }
          }}
          content={
            <div className="w-[min(340px,80vw)]">
              <div className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-2 text-sm font-medium text-[var(--color-text-1)]">
                {detailTitle}
              </div>
              <div className="max-h-[240px] overflow-auto whitespace-pre-wrap break-words px-3 py-2 text-sm leading-5 text-[var(--color-text-2)]">
                {detailText}
              </div>
            </div>
          }
        >
          <button
            type="button"
            className="shrink-0 border-0 bg-transparent p-0 text-sm leading-5 text-[var(--color-primary)] hover:underline"
          >
            {viewDetailLabel}
          </button>
        </Popover>
      ) : null}
      <button
        type="button"
        aria-label={closeLabel}
        className="shrink-0 border-0 bg-transparent p-0 text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
        onClick={onClose}
      >
        <CloseOutlined className="text-xs" />
      </button>
    </div>
  );
};

const genPresets = (presets = presetPalettes) => {
  return Object.entries(presets).map<Presets>(([label, colors]) => ({
    label,
    colors,
    key: label
  }));
};

const INIT_UNIT_ITEM = { name: null, id: null, color: '#000000' };
const INIT_DIMENSION: DimensionItem = { name: '', description: '' };

const normalizeDimensions = (items?: DimensionItem[]): DimensionItem[] => {
  if (!items?.length) {
    return [{ ...INIT_DIMENSION }];
  }
  return items.map((item) => ({
    name: item.name || '',
    description:
      typeof item.description === 'string'
        ? item.description
        : item.name || ''
  }));
};

const buildMetricSnippet = (metricName: string) => metricName;

const MetricModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, groupList, monitorObject, pluginId }, ref) => {
    const { post, put } = useApiClient();
    const { getMetricsGroup, getVmMetricNames, testMetricQuery } =
      useMonitorApi();
    const { t } = useTranslation();
    const { token } = theme.useToken();
    const presets = genPresets({
      primary: generate(token.colorPrimary),
      red,
      green
    });
    const formRef = useRef<FormInstance>(null);
    const commonContext = useCommon();
    const unitList = useMemo(
      () =>
        (commonContext?.groupedUnitList || []).map((item: any) => ({
          ...item,
          value: item.label
        })),
      [commonContext?.groupedUnitList]
    );
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<MetricInfo>({});
    const [groupOptions, setGroupOptions] = useState<ListItem[]>(groupList);
    const [groupLoading, setGroupLoading] = useState(false);
    const groupSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
      null
    );
    const selectedGroupIdRef = useRef<React.Key | null>(null);
    const allowInheritedGroupsRef = useRef(false);
    const groupRequestGenerationRef = useRef(0);
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [dimensions, setDimensions] = useState<DimensionItem[]>([
      { ...INIT_DIMENSION }
    ]);
    const [dimensionMode, setDimensionMode] = useState<DimensionMode>('input');
    const [dimensionLabelKeys, setDimensionLabelKeys] = useState<string[]>([]);
    const [enumList, setEnumList] = useState<EnumItem[]>([]);
    const [metricPickerOpen, setMetricPickerOpen] = useState(false);
    const [metricNames, setMetricNames] = useState<string[]>([]);
    const [metricNamesLoading, setMetricNamesLoading] = useState(false);
    const [metricSearch, setMetricSearch] = useState('');
    const [testLoading, setTestLoading] = useState(false);
    const [formulaTestStatus, setFormulaTestStatus] =
      useState<FormulaTestStatus>('idle');
    const lastProbedQueryRef = useRef<string>('');
    const metricSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
      null
    );
    const metricRequestGenerationRef = useRef(0);
    const isView = type === 'view';

    const resetDimensionGuideState = () => {
      setDimensionMode('input');
      setDimensionLabelKeys([]);
    };

    const clearFormulaProbeCache = () => {
      lastProbedQueryRef.current = '';
      setFormulaTestStatus('idle');
    };

    const markFormulaProbeAllowed = (normalizedQuery: string) => {
      lastProbedQueryRef.current = normalizedQuery;
      setFormulaTestStatus('passed');
    };

    const showFormulaErrorToast = (summary: string, detail?: string) => {
      const detailText = (detail || '').trim();
      const hasDetail = !!detailText && detailText !== summary.trim();
      message.error({
        key: METRIC_FORMULA_ERROR_TOAST_KEY,
        className:
          'metric-query-error-toast [&_.ant-message-notice-content]:!w-fit [&_.ant-message-custom-content]:!items-baseline [&_.ant-message-custom-content]:!gap-2',
        content: (
          <MetricQueryErrorToast
            summary={summary}
            detail={detail}
            viewDetailLabel={t('monitor.integrations.viewErrorDetail')}
            detailTitle={t('monitor.integrations.errorDetailTitle')}
            closeLabel={t('common.close')}
            onClose={() => message.destroy(METRIC_FORMULA_ERROR_TOAST_KEY)}
          />
        ),
        duration: hasDetail ? 10 : 4
      });
    };

    const applyMetricSaveFieldErrors = (error: unknown): boolean => {
      if (!(error instanceof HandledRequestError)) {
        return false;
      }
      const duplicateIdMessage = t('monitor.integrations.duplicateMetricId');
      const isUniqueTogetherNoise = (text: string) =>
        /必须能构成唯一集合|unique set|params_error/i.test(text);

      const payload = error.payload as
        | { data?: { errors?: Record<string, string[] | string> } }
        | undefined;
      const fieldErrors = payload?.data?.errors;

      const formFields: Array<{ name: string; errors: string[] }> = [];
      const leftover: string[] = [];

      if (fieldErrors && typeof fieldErrors === 'object') {
        Object.entries(fieldErrors).forEach(([field, value]) => {
          const messages = (Array.isArray(value) ? value : [value])
            .map((item) => String(item || '').trim())
            .filter(Boolean);
          if (!messages.length) return;

          if (
            field === 'params_error' &&
            messages.some((item) => isUniqueTogetherNoise(item))
          ) {
            formFields.push({ name: 'name', errors: [duplicateIdMessage] });
            return;
          }

          if (
            [
              'name',
              'display_name',
              'metric_group',
              'query',
              'data_type',
              'unit',
              'display_description',
              'description'
            ].includes(field)
          ) {
            formFields.push({ name: field, errors: messages });
          } else {
            leftover.push(...messages);
          }
        });
      } else if (error.message && isUniqueTogetherNoise(error.message)) {
        formFields.push({ name: 'name', errors: [duplicateIdMessage] });
      } else {
        return false;
      }

      if (formFields.length) {
        formRef.current?.setFields(formFields);
      }
      if (leftover.length) {
        message.error(leftover.join('; '));
      }
      return formFields.length > 0 || leftover.length > 0;
    };

    const loadGroupOptions = async (keyword = '') => {
      const generation = groupRequestGenerationRef.current + 1;
      groupRequestGenerationRef.current = generation;
      setGroupLoading(true);
      try {
        const page = await getMetricsGroup({
          monitor_object_id: monitorObject,
          monitor_plugin_id: pluginId,
          ...(keyword.trim() ? { keyword: keyword.trim() } : {})
        });
        const items = page.items.filter(
          (item) =>
            allowInheritedGroupsRef.current ||
            String(item.monitor_plugin) === String(pluginId)
        ) as ListItem[];
        const selectedGroup = groupList.find(
          (item) => String(item.id) === String(selectedGroupIdRef.current)
        );
        if (groupRequestGenerationRef.current !== generation) return;
        setGroupOptions(
          selectedGroup && !items.some((item) => item.id === selectedGroup.id)
            ? [...items, selectedGroup]
            : items
        );
      } catch {
        if (groupRequestGenerationRef.current === generation) {
          setGroupOptions(groupList);
        }
      } finally {
        if (groupRequestGenerationRef.current === generation) {
          setGroupLoading(false);
        }
      }
    };

    const handleGroupSearch = (value: string) => {
      if (groupSearchTimerRef.current) {
        clearTimeout(groupSearchTimerRef.current);
      }
      groupSearchTimerRef.current = setTimeout(() => {
        loadGroupOptions(value);
      }, 300);
    };

    const loadVmMetricNames = async (keyword = '') => {
      const generation = metricRequestGenerationRef.current + 1;
      metricRequestGenerationRef.current = generation;
      setMetricNamesLoading(true);
      try {
        const names = await getVmMetricNames({
          monitor_object_id: monitorObject,
          monitor_plugin_id: pluginId,
          ...(keyword.trim() ? { keyword: keyword.trim() } : {})
        });
        if (metricRequestGenerationRef.current !== generation) return;
        setMetricNames(Array.isArray(names) ? names : []);
      } catch {
        if (metricRequestGenerationRef.current === generation) {
          setMetricNames([]);
        }
      } finally {
        if (metricRequestGenerationRef.current === generation) {
          setMetricNamesLoading(false);
        }
      }
    };

    const handleMetricSearch = (value: string) => {
      setMetricSearch(value);
      if (metricSearchTimerRef.current) {
        clearTimeout(metricSearchTimerRef.current);
      }
      metricSearchTimerRef.current = setTimeout(() => {
        void loadVmMetricNames(value);
      }, 300);
    };

    useEffect(
      () => () => {
        if (groupSearchTimerRef.current) {
          clearTimeout(groupSearchTimerRef.current);
        }
        if (metricSearchTimerRef.current) {
          clearTimeout(metricSearchTimerRef.current);
        }
      },
      []
    );

    useEffect(() => {
      setGroupOptions(groupList);
    }, [groupList]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title }) => {
        const formData = cloneDeep(form);
        allowInheritedGroupsRef.current = type === 'view';
        selectedGroupIdRef.current =
          (formData.metric_group as React.Key) || null;
        setGroupVisible(true);
        void loadGroupOptions();
        setType(type);
        setTitle(title);
        resetDimensionGuideState();
        clearFormulaProbeCache();
        setMetricPickerOpen(false);
        setMetricSearch('');
        setMetricNames([]);
        try {
          if (type === 'add') {
            formData.type = 'metric';
            setDimensions([{ ...INIT_DIMENSION }]);
            setEnumList([INIT_UNIT_ITEM]);
          } else {
            setDimensions(
              normalizeDimensions(formData.dimensions as DimensionItem[])
            );
            if (formData.data_type === 'Number') {
              formData.unit = findCascaderPath(
                unitList,
                formData.unit as string
              );
            } else {
              formData.data_type = 'Enum';
              const _enumList = JSON.parse(formData.unit as string).map(
                (item: EnumItem) =>
                  Object.assign({ name: null, id: null, color: null }, item)
              );
              setEnumList(_enumList);
            }
          }
          if (typeof formData.query === 'string') {
            formData.query = stripMetricLabelsPlaceholder(formData.query);
          }
          setGroupForm(formData);
        } catch {
          if (typeof formData.query === 'string') {
            formData.query = stripMetricLabelsPlaceholder(formData.query);
          }
          setGroupForm(formData);
          setEnumList([{ name: null, id: null, color: null }]);
        }
      }
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    const operateGroup = async (params: MetricInfo) => {
      const msg: string = t(
        type === 'add'
          ? 'common.successfullyAdded'
          : 'common.successfullyModified'
      );
      const url: string =
        type === 'add'
          ? '/monitor/api/metrics/'
          : `/monitor/api/metrics/${groupForm.id}/`;
      const requestType = type === 'add' ? post : put;
      try {
        await requestType(url, params, {
          suppressErrorNotification: true
        });
      } catch (error) {
        if (!applyMetricSaveFieldErrors(error)) {
          if (error instanceof HandledRequestError && error.message) {
            message.error(error.message);
          }
        }
        return;
      }
      message.success(msg);
      handleCancel();
      onSuccess();
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then(async (values) => {
        const query = String(values.query || '');
        if (!query.trim()) {
          message.warning(t('common.required'));
          return;
        }

        const normalizedQuery = ensureMetricLabelsPlaceholder(query);
        const canSkipProbe =
          formulaTestStatus === 'passed' &&
          lastProbedQueryRef.current === normalizedQuery;

        setConfirmLoading(true);
        try {
          if (!canSkipProbe) {
            let result;
            try {
              result = await testMetricQuery({
                query: normalizedQuery,
                monitor_object_id: monitorObject,
                monitor_plugin_id: pluginId
              });
            } catch {
              lastProbedQueryRef.current = '';
              setFormulaTestStatus('failed');
              resetDimensionGuideState();
              message.error(t('monitor.integrations.confirmBlockedByFailedTest'));
              return;
            }

            if (!result?.ok) {
              if (result?.reason === 'syntax_error') {
                lastProbedQueryRef.current = '';
                setFormulaTestStatus('failed');
                resetDimensionGuideState();
                showFormulaErrorToast(
                  t('monitor.integrations.confirmSyntaxError'),
                  result.message
                );
                return;
              }
              if (result?.reason === 'no_data') {
                resetDimensionGuideState();
                markFormulaProbeAllowed(normalizedQuery);
                message.warning(t('monitor.integrations.confirmNoDataWarning'));
              } else {
                lastProbedQueryRef.current = '';
                setFormulaTestStatus('failed');
                resetDimensionGuideState();
                message.error(
                  t('monitor.integrations.confirmBlockedByFailedTest')
                );
                return;
              }
            } else {
              const keys = Array.isArray(result.label_keys)
                ? result.label_keys
                : [];
              setDimensionLabelKeys(keys);
              markFormulaProbeAllowed(normalizedQuery);
              if (keys.length) {
                setDimensionMode('select');
              }
            }
          }

          const cleanedDimensions = dimensions
            .filter((item) => item.name?.trim())
            .map((item) => ({
              name: item.name.trim(),
              description: (item.description || item.name).trim()
            }));
          await operateGroup({
            ...values,
            query: normalizedQuery,
            dimensions: cleanedDimensions,
            monitor_object: monitorObject,
            monitor_plugin: pluginId,
            type: 'metric',
            unit:
              values.data_type === 'Enum'
                ? JSON.stringify(enumList)
                : values.unit.at(-1)
          });
        } finally {
          setConfirmLoading(false);
        }
      });
    };

    const addDimension = () => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions.push({ ...INIT_DIMENSION });
      setDimensions(_dimensions);
    };

    const addEnumItem = () => {
      const _enumList = cloneDeep(enumList);
      _enumList.push(INIT_UNIT_ITEM);
      setEnumList(_enumList);
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setMetricPickerOpen(false);
      clearFormulaProbeCache();
      resetDimensionGuideState();
    };

    const validateEnumList = async () => {
      if (
        enumList.length &&
        enumList.some((item) => {
          return Object.values(item).some((tex) => !tex && tex !== 0);
        })
      ) {
        return Promise.reject(new Error(t('common.valueValidate')));
      }
      return Promise.resolve();
    };

    const onFormulaChange = () => {
      if (dimensionMode === 'select') {
        resetDimensionGuideState();
      }
      clearFormulaProbeCache();
    };

    const appendMetricToFormula = (metricName: string) => {
      const current = String(formRef.current?.getFieldValue('query') || '');
      const snippet = buildMetricSnippet(metricName);
      const next =
        current && !/\s$/.test(current)
          ? `${current} ${snippet}`
          : `${current}${snippet}`;
      formRef.current?.setFieldsValue({ query: next });
      resetDimensionGuideState();
      clearFormulaProbeCache();
      setMetricPickerOpen(false);
    };

    const handleSelectMetricOpenChange = (open: boolean) => {
      setMetricPickerOpen(open);
      if (open) {
        setMetricSearch('');
        void loadVmMetricNames();
      }
    };

    const handleTestMetric = async () => {
      const query = String(formRef.current?.getFieldValue('query') || '');
      if (!query.trim()) {
        message.warning(t('common.required'));
        return;
      }
      setTestLoading(true);
      try {
        const normalizedQuery = ensureMetricLabelsPlaceholder(query);
        const result = await testMetricQuery({
          query: normalizedQuery,
          monitor_object_id: monitorObject,
          monitor_plugin_id: pluginId
        });
        if (result?.ok) {
          const keys = Array.isArray(result.label_keys) ? result.label_keys : [];
          setDimensionLabelKeys(keys);
          markFormulaProbeAllowed(normalizedQuery);
          if (keys.length) {
            setDimensionMode('select');
            message.success(t('monitor.integrations.testMetricSuccess'));
          } else {
            resetDimensionGuideState();
            message.success(t('monitor.integrations.testMetricSuccessNoFields'));
          }
          return;
        }

        resetDimensionGuideState();
        if (result?.reason === 'syntax_error') {
          lastProbedQueryRef.current = '';
          setFormulaTestStatus('failed');
          showFormulaErrorToast(
            t('monitor.integrations.testMetricSyntaxError'),
            result.message
          );
        } else if (result?.reason === 'no_data') {
          markFormulaProbeAllowed(normalizedQuery);
          message.warning(t('monitor.integrations.testMetricNoData'));
        } else {
          lastProbedQueryRef.current = '';
          setFormulaTestStatus('failed');
          message.warning(t('monitor.integrations.testMetricFailed'));
        }
      } catch {
        resetDimensionGuideState();
        lastProbedQueryRef.current = '';
        setFormulaTestStatus('failed');
        message.warning(t('monitor.integrations.testMetricFailed'));
      } finally {
        setTestLoading(false);
      }
    };

    const onDimensionIdChange = (value: string, index: number) => {
      const _dimensions = cloneDeep(dimensions);
      const prevName = _dimensions[index].name || '';
      const prevDescription = _dimensions[index].description || '';
      _dimensions[index].name = value;
      if (!prevDescription || prevDescription === prevName) {
        _dimensions[index].description = value;
      }
      setDimensions(_dimensions);
    };

    const onDimensionDisplayNameChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions[index].description = e.target.value;
      setDimensions(_dimensions);
    };

    const deleteDimensiontem = (index: number) => {
      const _dimensions = cloneDeep(dimensions);
      _dimensions.splice(index, 1);
      setDimensions(_dimensions);
    };

    const handleEnumIdChange = (val: number | null, index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].id = val;
      setEnumList(_enumList);
    };

    const handleEnumNameChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].name = e.target.value;
      setEnumList(_enumList);
    };

    const handleEnumColorChange = (value: AggregationColor, index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList[index].color = value.toHexString();
      setEnumList(_enumList);
    };

    const deleteEnumItem = (index: number) => {
      const _enumList = cloneDeep(enumList);
      _enumList.splice(index, 1);
      setEnumList(_enumList);
    };

    const formatDimensionViewText = () => {
      const items = dimensions.filter((item) => item.name);
      if (!items.length) return '--';
      return items
        .map((item) =>
          item.description && item.description !== item.name
            ? `${item.name} (${item.description})`
            : item.name
        )
        .join(', ');
    };

    const metricPickerContent = (
      <div className="w-[min(520px,80vw)] min-w-[280px]">
        <Input
          allowClear
          value={metricSearch}
          placeholder={t('monitor.integrations.searchMetricNamePlaceholder')}
          onChange={(e) => handleMetricSearch(e.target.value)}
          className="mb-2"
        />
        <p className="mb-2 text-xs leading-5 text-[var(--color-text-3)]">
          {t('monitor.integrations.selectMetricRawOnlyHint')}
        </p>
        <Spin spinning={metricNamesLoading}>
          <div className="max-h-[280px] overflow-auto">
            {metricNames.length ? (
              metricNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  title={name}
                  className="block w-full break-all border-0 bg-transparent px-2 py-1.5 text-left text-sm leading-5 text-[var(--color-text-1)] hover:bg-[var(--color-bg-hover)]"
                  onClick={() => appendMetricToFormula(name)}
                >
                  {name}
                </button>
              ))
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  metricSearch.trim()
                    ? t('monitor.integrations.noVmMetricNamesForSearch')
                    : t('monitor.integrations.noVmMetricNames')
                }
              />
            )}
          </div>
        </Spin>
      </div>
    );

    const renderDimensionIdControl = (item: DimensionItem, index: number) => {
      if (dimensionMode === 'select' && dimensionLabelKeys.length) {
        return (
          <Select
            showSearch
            allowClear
            className="w-[42%]"
            value={item.name || undefined}
            placeholder={t('monitor.integrations.dimensionId')}
            options={dimensionLabelKeys.map((key) => ({
              label: key,
              value: key
            }))}
            onChange={(value) => onDimensionIdChange(value || '', index)}
          />
        );
      }
      return (
        <Input
          className="w-[42%]"
          value={item.name}
          placeholder={t('monitor.integrations.dimensionId')}
          onChange={(e) => onDimensionIdChange(e.target.value, index)}
        />
      );
    };

    return (
      <div>
        <OperateModal
          width={720}
          title={title}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            isView ? (
              <Button onClick={handleCancel}>{t('common.close')}</Button>
            ) : (
              <div>
                <Button
                  className="mr-[10px]"
                  type="primary"
                  loading={confirmLoading}
                  onClick={handleSubmit}
                >
                  {t('common.confirm')}
                </Button>
                <Button onClick={handleCancel}>{t('common.cancel')}</Button>
              </div>
            )
          }
        >
          {isView ? (
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label={t('common.id')}>
                {groupForm.name || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.name')}>
                <div className="flex items-center gap-2">
                  <span>{groupForm.display_name || '--'}</span>
                  {groupForm.is_ifmib === true && (
                    <Tag className="m-0" color="blue">
                      IF-MIB
                    </Tag>
                  )}
                </div>
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.metricGroup')}>
                {groupOptions.find(
                  (item) => String(item.id) === String(groupForm.metric_group)
                )?.display_name || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.formula')}>
                <div className="whitespace-pre-wrap break-all">
                  {stripMetricLabelsPlaceholder(
                    String(groupForm.query || '')
                  ) || '--'}
                </div>
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.dimension')}>
                {formatDimensionViewText()}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.dataType')}>
                {groupForm.data_type || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.unit')}>
                {groupForm.data_type === 'Enum'
                  ? enumList
                    .map((item) => `${item.id}: ${item.name}`)
                    .join(', ') || '--'
                  : Array.isArray(groupForm.unit)
                    ? groupForm.unit.at(-1) || '--'
                    : groupForm.unit || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.description')}>
                <div className="whitespace-pre-wrap break-words">
                  {groupForm.display_description ||
                    groupForm.description ||
                    '--'}
                </div>
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Form
              ref={formRef}
              name="basic"
              labelCol={{ span: 4 }}
              wrapperCol={{ span: 18 }}
            >
              <Form.Item<MetricInfo>
                label={t('common.id')}
                name="name"
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Input disabled={type === 'edit'} />
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('common.name')}
                name="display_name"
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Input />
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('monitor.integrations.metricGroup')}
                name="metric_group"
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Select
                  showSearch
                  filterOption={false}
                  loading={groupLoading}
                  onSearch={handleGroupSearch}
                  onDropdownVisibleChange={(open) =>
                    !open && handleGroupSearch('')
                  }
                >
                  {groupOptions.map((item) => (
                    <Option key={item.id} value={item.id}>
                      {item.display_name}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('monitor.integrations.formula')}
                name="query"
                rules={[{ required: true, message: t('common.required') }]}
                extra={
                  <div className="mt-1 flex gap-4">
                    <Popover
                      trigger="click"
                      open={metricPickerOpen}
                      onOpenChange={handleSelectMetricOpenChange}
                      content={metricPickerContent}
                      placement="bottomLeft"
                    >
                      <Button type="link" className="h-auto px-0">
                        {t('monitor.integrations.selectMetric')}
                      </Button>
                    </Popover>
                    <Button
                      type="link"
                      className="h-auto px-0"
                      loading={testLoading}
                      onClick={handleTestMetric}
                    >
                      {t('monitor.integrations.testMetric')}
                    </Button>
                  </div>
                }
              >
                <Input.TextArea rows={4} onChange={onFormulaChange} />
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('monitor.integrations.dimension')}
                name="dimensions"
              >
                <ul>
                  {dimensions.map((item, index) => (
                    <li
                      className={`flex items-center ${
                        index + 1 !== dimensions?.length && 'mb-[10px]'
                      }`}
                      key={index}
                    >
                      {renderDimensionIdControl(item, index)}
                      <Input
                        className="ml-[10px] w-[37%]"
                        value={item.description}
                        placeholder={t(
                          'monitor.integrations.dimensionDisplayName'
                        )}
                        onChange={(e) =>
                          onDimensionDisplayNameChange(e, index)
                        }
                      />
                      <Button
                        icon={<PlusOutlined />}
                        className="ml-[10px]"
                        onClick={addDimension}
                      ></Button>
                      {!!index && (
                        <Button
                          icon={<MinusOutlined />}
                          className="ml-[10px]"
                          onClick={() => deleteDimensiontem(index)}
                        ></Button>
                      )}
                    </li>
                  ))}
                </ul>
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('monitor.integrations.dataType')}
                name="data_type"
                rules={[{ required: true, message: t('common.required') }]}
              >
                <Select>
                  <Option value="Number">
                    {t('monitor.integrations.number')}
                  </Option>
                  <Option value="Enum">
                    {t('monitor.integrations.enum')}
                  </Option>
                </Select>
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.data_type !== currentValues.data_type
                }
              >
                {({ getFieldValue }) => {
                  const dataType = getFieldValue('data_type');
                  if (!dataType) return null;
                  return dataType === 'Number' ? (
                    <Form.Item<MetricInfo>
                      label={t('common.unit')}
                      name="unit"
                      rules={[
                        { required: true, message: t('common.required') }
                      ]}
                    >
                      <Cascader showSearch options={unitList} />
                    </Form.Item>
                  ) : (
                    <Form.Item<MetricInfo>
                      label={t('common.unit')}
                      name="unit"
                      rules={[{ required: true, validator: validateEnumList }]}
                    >
                      <ul>
                        <li className="mb-[6px] text-[var(--color-text-3)] font-[600]">
                          <div className="w-[80%] flex justify-between">
                            <span className="w-[160px]">
                              {t('monitor.integrations.originalValue')}
                            </span>
                            <span className="w-[160px] ml-2">
                              {t('monitor.integrations.mappedValue')}
                            </span>
                            <span className="w-[160px] ml-2">
                              {t('monitor.integrations.color')}
                            </span>
                          </div>
                        </li>
                        {enumList.map((item, index) => (
                          <li
                            className={`flex ${
                              index + 1 !== enumList?.length && 'mb-[10px]'
                            }`}
                            key={index}
                          >
                            <div className="w-[80%] flex justify-between">
                              <InputNumber
                                placeholder={t(
                                  'monitor.integrations.originalValue'
                                )}
                                className="w-[160px]"
                                min={0}
                                value={item.id}
                                onChange={(e) => handleEnumIdChange(e, index)}
                              />
                              <Input
                                placeholder={t(
                                  'monitor.integrations.mappedValue'
                                )}
                                className="w-[160px] ml-2"
                                value={item.name as string}
                                onChange={(e) => {
                                  handleEnumNameChange(e, index);
                                }}
                              />
                              <ColorPicker
                                className="w-[160px] ml-2"
                                value={item.color as string}
                                showText
                                presets={presets}
                                placement="bottom"
                                onChange={(value) => {
                                  handleEnumColorChange(value, index);
                                }}
                              />
                            </div>
                            <Button
                              icon={<PlusOutlined />}
                              className="ml-[10px]"
                              onClick={addEnumItem}
                            ></Button>
                            {!!index && (
                              <Button
                                icon={<MinusOutlined />}
                                className="ml-[10px]"
                                onClick={() => deleteEnumItem(index)}
                              ></Button>
                            )}
                          </li>
                        ))}
                      </ul>
                    </Form.Item>
                  );
                }}
              </Form.Item>
              <Form.Item<MetricInfo>
                label={t('common.description')}
                name="description"
              >
                <Input.TextArea rows={4} />
              </Form.Item>
            </Form>
          )}
        </OperateModal>
      </div>
    );
  }
);
MetricModal.displayName = 'MetricModal';
export default MetricModal;
