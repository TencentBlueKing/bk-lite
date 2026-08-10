/**
 * 共享单值配置 Hook
 * 供仪表盘 ViewConfig 和拓扑 NodeConfPanel 复用
 */
import { useState, useCallback, useEffect } from 'react';
import type { FormInstance } from 'antd';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';
import { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import { buildTreeData } from '@/app/ops-analysis/(pages)/view/topology/utils/dataTreeUtils';
import { canEnableCompare } from '@/app/ops-analysis/utils/compareQuery';
import { getDateRangeTimezone } from '@/app/ops-analysis/utils/dateRange';

interface UseSingleValueConfigProps {
  form: FormInstance;
  selectedDataSource: DatasourceItem | undefined;
  builtinNamespaceId?: number;
  /** 显式传入数据源 ID（当 selectedDataSource 可能尚未加载时使用） */
  dataSourceId?: number | null;
  getSourceDataByApiId: (
    id: number,
    params: Record<string, any>,
  ) => Promise<any>;
  /** 面板是否打开 */
  open?: boolean;
}

export function useSingleValueConfig({
  form,
  selectedDataSource,
  builtinNamespaceId,
  dataSourceId,
  getSourceDataByApiId,
  open = true,
}: UseSingleValueConfigProps) {
  const { t } = useTranslation();
  const [singleValueTreeData, setSingleValueTreeData] = useState<any[]>([]);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [loadingSingleValueData, setLoadingSingleValueData] = useState(false);
  const [thresholdColors, setThresholdColors] =
    useState<ThresholdColorConfig[]>(DEFAULT_THRESHOLD_COLORS);

  // 当数据源不再支持 compare 时，自动关闭
  const compareAvailable = canEnableCompare({
    config: { chartType: 'single', dataSourceParams: selectedDataSource?.params },
    dataSource: selectedDataSource,
  });

  useEffect(() => {
    if (open && !compareAvailable && form.getFieldValue('compare')) {
      form.setFieldsValue({ compare: false });
    }
  }, [open, compareAvailable, selectedDataSource, form]);

  const handleThresholdChange = useCallback(
    (index: number, field: 'value' | 'color', value: string | number) => {
      setThresholdColors((prev) => {
        const newThresholds = [...prev];
        newThresholds[index] = {
          ...newThresholds[index],
          [field]: field === 'value' ? String(value) : value,
        };
        return newThresholds;
      });
    },
    [],
  );

  const handleThresholdBlur = useCallback(
    (index: number, value: number | null) => {
      setThresholdColors((prev) => {
        const newThresholds = [...prev];
        if (value === null || value === undefined) {
          newThresholds[index] = { ...newThresholds[index], value: '50' };
          return newThresholds;
        }
        const numValue = Number(value);
        const isDuplicate = prev.some(
          (threshold, i) =>
            i !== index && parseFloat(threshold.value) === numValue,
        );
        if (isDuplicate) {
          let adjustedValue = numValue;
          while (
            prev.some(
              (threshold, i) =>
                i !== index && parseFloat(threshold.value) === adjustedValue,
            )
          ) {
            adjustedValue += 1;
          }
          newThresholds[index] = {
            ...newThresholds[index],
            value: adjustedValue.toString(),
          };
        } else {
          newThresholds[index] = {
            ...newThresholds[index],
            value: numValue.toString(),
          };
        }
        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value),
        );
      });
    },
    [],
  );

  const addThreshold = useCallback((afterIndex?: number) => {
    setThresholdColors((prev) => {
      let newValue = 50;
      if (afterIndex !== undefined && afterIndex >= 0) {
        const currentValue = parseFloat(prev[afterIndex]?.value || '0');
        const nextValue =
          afterIndex + 1 < prev.length
            ? parseFloat(prev[afterIndex + 1]?.value || '0')
            : 0;
        if (currentValue - nextValue > 1) {
          newValue = Math.floor((currentValue + nextValue) / 2);
        } else {
          newValue = Math.max(currentValue - 5, nextValue + 1);
        }
      } else {
        const values = prev
          .map((t) => parseFloat(t.value))
          .filter((v) => !isNaN(v));
        const maxValue = Math.max(...values);
        newValue = Math.min(maxValue + 10, 100);
      }
      const existingValues = prev
        .map((t) => parseFloat(t.value))
        .filter((v) => !isNaN(v));
      while (existingValues.includes(newValue)) {
        newValue += 1;
      }
      const newThreshold = { color: '#fd666d', value: newValue.toString() };
      if (afterIndex !== undefined && afterIndex >= 0) {
        const newThresholds = [...prev];
        newThresholds.splice(afterIndex + 1, 0, newThreshold);
        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value),
        );
      } else {
        const newThresholds = [...prev, newThreshold];
        return newThresholds.sort(
          (a, b) => parseFloat(b.value) - parseFloat(a.value),
        );
      }
    });
  }, []);

  const removeThreshold = useCallback((index: number) => {
    setThresholdColors((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const fetchSingleValueDataFields = useCallback(async () => {
    const resolvedId = dataSourceId ?? selectedDataSource?.id;
    if (!resolvedId || !selectedDataSource) return;

    setLoadingSingleValueData(true);
    try {
      const formValues = form.getFieldsValue();
      const userParams = formValues?.params || {};
      const requestParams = processDataSourceParams({
        sourceParams: selectedDataSource.params,
        userParams,
        resolutionContext: {
          referenceNow: Date.now(),
          timezone: getDateRangeTimezone(),
        },
      });

      if (
        builtinNamespaceId !== undefined &&
        Array.isArray(selectedDataSource.namespaces) &&
        selectedDataSource.namespaces.length > 0
      ) {
        requestParams.namespace_id = builtinNamespaceId;
      }

      const data = await getSourceDataByApiId(resolvedId, requestParams);
      const tree = buildTreeData(data, selectedDataSource.field_schema);
      setSingleValueTreeData(tree);
    } catch (error) {
      console.error('Failed to fetch data fields:', error);
      message.error(t('dashboard.fetchDataFieldsFailed'));
    } finally {
      setLoadingSingleValueData(false);
    }
  }, [selectedDataSource, dataSourceId, form, getSourceDataByApiId, builtinNamespaceId]);

  const handleSingleValueFieldChange = useCallback(
    (checkedKeys: any) => {
      const keys = Array.isArray(checkedKeys)
        ? checkedKeys
        : checkedKeys.checked;
      const findNode = (nodes: any[], targetKey: string): any => {
        for (const node of nodes) {
          if (node.key === targetKey) return node;
          if (node.children) {
            const found = findNode(node.children, targetKey);
            if (found) return found;
          }
        }
        return null;
      };
      const leafKeys = keys.filter((key: string) => {
        const node = findNode(singleValueTreeData, key);
        return node && node.isLeaf;
      });
      const newSelectedFields =
        leafKeys.length > 0 ? [leafKeys[leafKeys.length - 1]] : [];
      setSelectedFields(newSelectedFields);
      form.setFieldsValue({ selectedFields: newSelectedFields });
    },
    [singleValueTreeData, form],
  );

  const resetSingleValueConfig = useCallback(() => {
    setSingleValueTreeData([]);
    setSelectedFields([]);
    setLoadingSingleValueData(false);
    setThresholdColors(DEFAULT_THRESHOLD_COLORS);
  }, []);

  return {
    singleValueTreeData,
    setSingleValueTreeData,
    selectedFields,
    setSelectedFields,
    loadingSingleValueData,
    thresholdColors,
    setThresholdColors,
    compareAvailable,
    handleThresholdChange,
    handleThresholdBlur,
    addThreshold,
    removeThreshold,
    fetchSingleValueDataFields,
    handleSingleValueFieldChange,
    resetSingleValueConfig,
  };
}
