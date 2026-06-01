import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  forwardRef,
  useImperativeHandle,
  useCallback,
} from 'react';
import { v4 as uuidv4 } from 'uuid';
import ViewSelector from './components/viewSelector';
import ViewConfig from './components/viewConfig';
import GridLayout, { WidthProvider } from 'react-grid-layout';
import {
  Button,
  Empty,
  Dropdown,
  Menu,
  Modal,
  message,
  Spin,
  Tooltip,
  Select,
  Tag,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useCanvasResources } from '@/app/ops-analysis/hooks/useCanvasResources';
import dayjs from 'dayjs';
import {
  LayoutItem,
  OtherConfig,
  LayoutChangeItem,
  WidgetConfig,
  UnifiedFilterDefinition,
  FilterValue,
  FilterBindings,
  TimeRangeValue,
} from '@/app/ops-analysis/types/dashBoard';
import { DirItem } from '@/app/ops-analysis/types';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useUnifiedFilter } from '@/app/ops-analysis/hooks/useUnifiedFilter';
import {
  PlusOutlined,
  MoreOutlined,
  EditOutlined,
  ReloadOutlined,
  SettingOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { useDashBoardApi } from '@/app/ops-analysis/api/dashBoard';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import WidgetWrapper from './components/widgetWrapper';
import PermissionWrapper from '@/components/permission';
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from '@/app/ops-analysis/components/unifiedFilter';
import {
  getFilterDefinitionId,
  getBindableFilterParams,
  buildDefaultFilterBindings,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  collectNamespaceOptions,
} from '@/app/ops-analysis/utils/namespaceFilter';
import {
  collectDashboardDataSourceIds,
  collectDashboardNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import { exportDashboardToPdf } from '@/app/ops-analysis/utils/exportPdf';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

interface DashboardProps {
  selectedDashboard?: DirItem | null;
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const ResponsiveGridLayout = WidthProvider(GridLayout) as any;

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  ({ selectedDashboard }, ref) => {
    const { t } = useTranslation();
    const themeName = resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const isDarkTheme = themeName === 'dark';
    const { getDashboardDetail, saveDashboard } = useDashBoardApi();
    const dataSourceManager = useDataSourceManager();
    const {
      namespaceList,
      loadCanvasNamespaces,
    } = useOpsAnalysis();
    const { syncCanvasResources } = useCanvasResources();
    const [isEditMode, setIsEditMode] = useState(false);
    const [addModalVisible, setAddModalVisible] = useState(false);
    const [layout, setLayout] = useState<LayoutItem[]>([]);
    const [originalLayout, setOriginalLayout] = useState<LayoutItem[]>([]);
    const [configDrawerVisible, setConfigDrawerVisible] = useState(false);
    const [currentConfigItem, setCurrentConfigItem] = useState<LayoutItem>();
    const [isNewComponentConfig, setIsNewComponentConfig] = useState(false);
    const [dashboardReloadVersion, setDashboardReloadVersion] = useState(0);
    const [widgetReloadVersions, setWidgetReloadVersions] = useState<
      Record<string, number>
    >({});
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(false);
    const [otherConfig, setOtherConfig] = useState<OtherConfig>({});
    const [originalOtherConfig, setOriginalOtherConfig] = useState<OtherConfig>(
      {}
    );
    const [filterConfigModalVisible, setFilterConfigModalVisible] =
      useState(false);
    const [namespaceDraftId, setNamespaceDraftId] = useState<
      number | undefined
    >(undefined);
    const [appliedFilterDefinitions, setAppliedFilterDefinitions] = useState<
      UnifiedFilterDefinition[]
    >([]);
    const [appliedFilterValues, setAppliedFilterValues] = useState<
      Record<string, FilterValue>
    >({});
    const [appliedNamespaceId, setAppliedNamespaceId] = useState<
      number | undefined
    >(undefined);
    const [filterSearchVersion, setFilterSearchVersion] = useState(0);
    const [namespaceSearchVersion, setNamespaceSearchVersion] = useState(0);
    const exportRef = useRef<HTMLDivElement>(null);
    const getDashboardDetailRef = useRef(getDashboardDetail);
    const [exporting, setExporting] = useState(false);

    useEffect(() => {
      getDashboardDetailRef.current = getDashboardDetail;
    }, [getDashboardDetail]);

    const {
      definitions,
      filterValues,
      setFilterValues,
      updateDefinitions,
      setDefinitions,
    } = useUnifiedFilter();
    const [originalDefinitions, setOriginalDefinitions] = useState<UnifiedFilterDefinition[]>([]);

    const applyQueryState = useCallback(
      (
        nextDefinitions: UnifiedFilterDefinition[],
        nextValues: Record<string, FilterValue>,
        nextNamespaceId: number | undefined,
      ) => {
        setAppliedFilterDefinitions(nextDefinitions);
        setAppliedFilterValues(nextValues);
        setAppliedNamespaceId(nextNamespaceId);
      },
      [],
    );

    const syncFilterStateAfterLayoutChange = useCallback(
      (
        nextDefinitions: UnifiedFilterDefinition[],
        nextDraftValues: Record<string, FilterValue>,
        nextAppliedValues: Record<string, FilterValue>,
      ) => {
        setDefinitions(nextDefinitions);
        setFilterValues(nextDraftValues);
        applyQueryState(nextDefinitions, nextAppliedValues, appliedNamespaceId);
      },
      [setDefinitions, setFilterValues, applyQueryState, appliedNamespaceId],
    );

    const syncDashboardCanvasResources = useCallback(async (
      nextLayout: LayoutItem[],
    ) => {
      return syncCanvasResources({
        source: nextLayout,
        getDataSourceIds: collectDashboardDataSourceIds,
        getNamespaceIds: collectDashboardNamespaceIds,
      });
    }, [syncCanvasResources]);

    const resolveLayoutNamespaceId = useCallback((
      nextLayout: LayoutItem[],
      canvasDataSources: DatasourceItem[],
    ) => {
      if (namespaceDraftId !== undefined) {
        return namespaceDraftId;
      }
      if (appliedNamespaceId !== undefined) {
        return appliedNamespaceId;
      }

      const namespaceIds = Array.from(
        collectDashboardNamespaceIds(nextLayout, canvasDataSources),
      );
      return namespaceIds[0];
    }, [appliedNamespaceId, namespaceDraftId]);

    const buildFiltersFromLayout = (
      nextLayout: LayoutItem[],
      previousDefinitions: UnifiedFilterDefinition[],
    ): UnifiedFilterDefinition[] => {
      const discoveredParams = new Map<
        string,
        ParamItem & { type: 'string' | 'timeRange' }
      >();

      nextLayout.forEach((item) => {
        const dataSourceId = item.valueConfig?.dataSource;
        const normalizedId =
          typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
        const dataSource = dataSourceManager.dataSources.find(
          (source) => source.id === normalizedId,
        );
        // 始终使用数据源的当前 params 来发现可绑定参数，
        // 而非 widget 保存时的快照（快照可能已过时）
        const params = dataSource?.params;

        getBindableFilterParams(params).forEach((param) => {
          const id = getFilterDefinitionId(param.name, param.type);
          if (!discoveredParams.has(id)) {
            discoveredParams.set(id, param);
          }
        });
      });

      const existingDefinitions = new Map(
        previousDefinitions.map((definition) => [definition.id, definition]),
      );

      return Array.from(discoveredParams.entries()).map(([id, param], index) => {
        const existing =
          existingDefinitions.get(id) ||
          previousDefinitions.find(
            (definition) =>
              definition.key === param.name && definition.type === param.type,
          );

        let defaultValue: FilterValue = null;
        if (existing?.defaultValue !== undefined) {
          defaultValue = existing.defaultValue;
        } else if (param.value !== undefined && param.value !== null) {
          if (param.type === 'timeRange' && typeof param.value === 'number') {
            const end = dayjs();
            const start = end.subtract(param.value, 'minute');
            defaultValue = { start: start.toISOString(), end: end.toISOString(), selectValue: param.value };
          } else {
            defaultValue = param.value as FilterValue;
          }
        }

        return {
          id,
          key: param.name,
          name: existing?.name || param.alias_name || param.name,
          type: param.type,
          defaultValue,
          order: index,
          enabled: existing?.enabled ?? true,
        };
      });
    };

    const syncLayoutFilterBindings = (
      nextLayout: LayoutItem[],
      definitions: UnifiedFilterDefinition[],
    ) => {
      const allowedIds = new Set(definitions.map((definition) => definition.id));

      return nextLayout.map((item) => {
        const existingBindings = item.valueConfig?.filterBindings;
        // 使用数据源当前 params 来决定绑定关系，而非保存时的快照
        const dataSourceId = item.valueConfig?.dataSource;
        const normalizedId =
          typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
        const dataSource = dataSourceManager.dataSources.find(
          (source) => source.id === normalizedId,
        );
        const currentParams = dataSource?.params;

        const autoBindings = buildDefaultFilterBindings(
          currentParams,
          definitions,
          existingBindings,
        );

        if (!autoBindings) {
          if (existingBindings === undefined) {
            return item;
          }
          return {
            ...item,
            valueConfig: {
              ...item.valueConfig,
              filterBindings: undefined,
            },
          };
        }

        const prunedBindings = Object.entries(autoBindings).reduce<FilterBindings>(
          (acc, [filterId, enabled]) => {
            if (allowedIds.has(filterId)) {
              acc[filterId] = enabled;
            }
            return acc;
          },
          {},
        );

        const newBindings = Object.keys(prunedBindings).length ? prunedBindings : undefined;
        
        if (JSON.stringify(existingBindings) === JSON.stringify(newBindings)) {
          return item;
        }

        return {
          ...item,
          valueConfig: {
            ...item.valueConfig,
            filterBindings: newBindings,
          },
        };
      });
    };

    const syncFilterValuesWithDefinitions = (
      nextDefinitions: UnifiedFilterDefinition[],
      currentValues: Record<string, FilterValue>,
    ): Record<string, FilterValue> => {
      const updatedValues: Record<string, FilterValue> = { ...currentValues };
      nextDefinitions.forEach((def) => {
        if (def.enabled && def.defaultValue !== null && def.defaultValue !== undefined) {
          if (updatedValues[def.id] === undefined || updatedValues[def.id] === null) {
            if (def.type === 'timeRange') {
              const rawValue = def.defaultValue;
              if (typeof rawValue === 'number') {
                const end = dayjs();
                const start = end.subtract(rawValue, 'minute');
                updatedValues[def.id] = {
                  start: start.toISOString(),
                  end: end.toISOString(),
                } as TimeRangeValue;
              } else if (
                rawValue &&
                typeof rawValue === 'object' &&
                'start' in rawValue &&
                'end' in rawValue
              ) {
                const trv = rawValue as TimeRangeValue;
                if (trv.selectValue && trv.selectValue > 0) {
                  const end = dayjs();
                  const start = end.subtract(trv.selectValue, 'minute');
                  updatedValues[def.id] = {
                    start: start.toISOString(),
                    end: end.toISOString(),
                    selectValue: trv.selectValue,
                  } as TimeRangeValue;
                } else {
                  updatedValues[def.id] = rawValue;
                }
              }
            } else {
              updatedValues[def.id] = def.defaultValue;
            }
          }
        }
      });
      return updatedValues;
    };

    const namespaceOptions = useMemo(() => {
      return collectNamespaceOptions(layout, dataSourceManager.dataSources, namespaceList);
    }, [layout, dataSourceManager.dataSources, namespaceList]);

    useEffect(() => {
      if (namespaceOptions.length > 0) {
        const fallbackNamespaceId = namespaceOptions[0].value;
        const draftValid =
          namespaceDraftId !== undefined &&
          namespaceOptions.some((o) => o.value === namespaceDraftId);
        const appliedValid =
          appliedNamespaceId !== undefined &&
          namespaceOptions.some((o) => o.value === appliedNamespaceId);

        if (!draftValid) {
          setNamespaceDraftId(fallbackNamespaceId);
        }
        if (!appliedValid) {
          setAppliedNamespaceId(fallbackNamespaceId);
        }
      } else {
        setNamespaceDraftId(undefined);
        setAppliedNamespaceId(undefined);
      }
    }, [namespaceOptions, namespaceDraftId, appliedNamespaceId]);

    const namespaceSelectorElement = useMemo(() => {
      if (namespaceOptions.length <= 1) return undefined;
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm text-(--color-text-2) whitespace-nowrap">
            {t('namespace.title')}:
          </span>
          <Select
            value={namespaceDraftId}
            onChange={(val: number) => {
              setNamespaceDraftId(val);
            }}
            options={namespaceOptions}
            style={{ minWidth: 160 }}
          />
        </div>
      );
    }, [namespaceOptions, namespaceDraftId, t]);

    useEffect(() => {
      const loadDashboardData = async () => {
        if (!selectedDashboard) {
          setLayout([]);
          setOriginalLayout([]);
          setOtherConfig({});
          setOriginalOtherConfig({});
          setDefinitions([]);
          setFilterValues({});
          setAppliedFilterDefinitions([]);
          setAppliedFilterValues({});
          setOriginalDefinitions([]);
          return;
        }
        try {
          setLoading(true);
          const dashboardData = await getDashboardDetailRef.current(
            selectedDashboard.data_id,
          );
          const nextLayout =
            dashboardData.view_sets && Array.isArray(dashboardData.view_sets)
              ? dashboardData.view_sets
              : [];
          await syncDashboardCanvasResources(nextLayout);
          if (
            dashboardData.view_sets &&
            Array.isArray(dashboardData.view_sets)
          ) {
            setLayout(nextLayout);
            setOriginalLayout([...nextLayout]);
          } else {
            setLayout([]);
            setOriginalLayout([]);
            void loadCanvasNamespaces([]);
          }

          const savedOtherConfig = dashboardData.other || {};
          setOtherConfig(savedOtherConfig);
          setOriginalOtherConfig({ ...savedOtherConfig });

          // Handle both legacy (unifiedFilters) and new (direct array) format
          const rawFilters = dashboardData.filters;
          const loadedDefinitions: UnifiedFilterDefinition[] =
            Array.isArray(rawFilters) ? rawFilters :
            (rawFilters?.definitions || rawFilters?.unifiedFilters || []);
          
          const initialValues = syncFilterValuesWithDefinitions(loadedDefinitions, {});

          setDefinitions(loadedDefinitions);
          setFilterValues(initialValues);
          setAppliedFilterDefinitions(loadedDefinitions);
          setAppliedFilterValues(initialValues);
          setOriginalDefinitions([...loadedDefinitions]);
        } catch (error) {
          console.error('加载仪表盘数据失败:', error);
          setLayout([]);
          setOriginalLayout([]);
          setOtherConfig({});
          setOriginalOtherConfig({});
          setDefinitions([]);
          setFilterValues({});
          setAppliedFilterDefinitions([]);
          setAppliedFilterValues({});
          setOriginalDefinitions([]);
        } finally {
          setLoading(false);
        }
      };
      loadDashboardData();
    }, [selectedDashboard?.data_id, loadCanvasNamespaces, syncDashboardCanvasResources]);

    // 监听 selectedDashboard 的变化，重置状态
    useEffect(() => {
      setIsEditMode(false);
      setAddModalVisible(false);
      setConfigDrawerVisible(false);
      setCurrentConfigItem(undefined);
      setIsNewComponentConfig(false);
      setSaving(false);
      setDashboardReloadVersion(0);
      setFilterSearchVersion(0);
      setNamespaceSearchVersion(0);
      setWidgetReloadVersions({});
      setAppliedFilterDefinitions([]);
      setAppliedFilterValues({});
      setNamespaceDraftId(undefined);
      setAppliedNamespaceId(undefined);
    }, [selectedDashboard?.data_id]);

    const openAddModal = () => {
      setIsEditMode(true);
      setAddModalVisible(true);
    };

    // 检查是否有未保存的更改
    const hasUnsavedChanges = () => {
      if (
        originalLayout.length === 0 &&
        layout.length === 0 &&
        Object.keys(originalOtherConfig).length === 0 &&
        Object.keys(otherConfig).length === 0 &&
        originalDefinitions.length === 0 &&
        definitions.length === 0
      ) {
        return false;
      }
      try {
        const layoutChanged =
          JSON.stringify(layout) !== JSON.stringify(originalLayout);
        const otherConfigChanged =
          JSON.stringify(otherConfig) !== JSON.stringify(originalOtherConfig);
        const filtersChanged =
          JSON.stringify(definitions) !==
          JSON.stringify(originalDefinitions);
        return layoutChanged || otherConfigChanged || filtersChanged;
      } catch (error) {
        console.error('检查未保存更改时出错:', error);
        return false;
      }
    };

    // 暴露方法给父组件
    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    const handleRefresh = () => {
      applyQueryState(definitions, filterValues, namespaceDraftId);
      setDashboardReloadVersion((prev) => prev + 1);
    };

    const handleExportPdf = useCallback(async () => {
      if (!exportRef.current) return;
      setExporting(true);
      try {
        await exportDashboardToPdf(
          exportRef.current,
          selectedDashboard?.name || 'dashboard'
        );
        message.success(t('dashboard.exportPdfSuccess'));
      } catch (err) {
        console.error('Export PDF failed:', err);
        message.error(t('dashboard.exportPdfFailed'));
      } finally {
        setExporting(false);
      }
    }, [selectedDashboard?.name, t]);

    const onLayoutChange = (newLayout: LayoutChangeItem[]) => {
      setLayout((prevLayout) => {
        return prevLayout.map((item) => {
          const newItem = newLayout.find((l) => l.i === item.i);
          if (newItem) {
            return { ...item, ...newItem };
          }
          return item;
        });
      });
    };

    const handleAddComponent = (config: WidgetConfig) => {
      const newWidget: LayoutItem = {
        i: uuidv4(),
        x: (layout.length % 3) * 4,
        y: Infinity,
        w: 4,
        h: 3,
        name: config?.name || '',
        description: config?.description || '',
        valueConfig: {
          dataSource: config.dataSource,
          chartType: config.chartType || '',
          dataSourceParams: config.dataSourceParams || [],
          tableConfig: config.tableConfig,
          filterBindings: config.filterBindings,
          selectedFields: config.selectedFields,
          topNLabelField: config.topNLabelField,
          topNValueField: config.topNValueField,
          unit: config.unit,
          conversionFactor: config.conversionFactor,
          decimalPlaces: config.decimalPlaces,
          thresholdColors: config.thresholdColors,
          compare: config.compare,
        },
      };
      const nextLayout = [...layout, newWidget];
      const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
      const syncedLayout = syncLayoutFilterBindings(nextLayout, nextDefinitions);
      const nextFilterValues = syncFilterValuesWithDefinitions(nextDefinitions, filterValues);
      const nextAppliedValues = syncFilterValuesWithDefinitions(
        nextDefinitions,
        appliedFilterValues,
      );

      setLayout(syncedLayout);
      void syncDashboardCanvasResources(syncedLayout).then((canvasDataSources) => {
        const nextNamespaceId = resolveLayoutNamespaceId(
          syncedLayout,
          canvasDataSources,
        );
        const shouldApplyNamespace =
          nextNamespaceId !== undefined || appliedNamespaceId === undefined;

        setDefinitions(nextDefinitions);
        setFilterValues(nextFilterValues);
        applyQueryState(
          nextDefinitions,
          nextAppliedValues,
          shouldApplyNamespace ? nextNamespaceId : appliedNamespaceId,
        );

        if (shouldApplyNamespace) {
          setNamespaceDraftId(nextNamespaceId);
        }
        if ((shouldApplyNamespace ? nextNamespaceId : appliedNamespaceId) !== appliedNamespaceId) {
          setNamespaceSearchVersion((prev) => prev + 1);
        }
        setAddModalVisible(false);
      });
    };

    const handleSave = async () => {
      if (!selectedDashboard) {
        message.warning('请先选择一个仪表盘');
        return;
      }

      try {
        setSaving(true);
        const saveData = {
          name: selectedDashboard.name,
          desc: selectedDashboard.desc || '',
          filters: definitions,
          other: otherConfig,
          view_sets: layout,
        };
        await saveDashboard(selectedDashboard.data_id, saveData);
        setOriginalLayout([...layout]);
        setOriginalOtherConfig({ ...otherConfig });
        setOriginalDefinitions([...definitions]);
        setIsEditMode(false);
        message.success(t('common.saveSuccess'));
      } catch (error) {
        console.error('保存仪表盘失败:', error);
      } finally {
        setSaving(false);
      }
    };

    const toggleEditMode = () => {
      setIsEditMode(!isEditMode);
    };

    const handleCancelEdit = () => {
      const revertedFilterValues = syncFilterValuesWithDefinitions(
        originalDefinitions,
        appliedFilterValues,
      );

      setLayout([...originalLayout]);
      void syncDashboardCanvasResources([...originalLayout]);
      setOtherConfig({ ...originalOtherConfig });
      setDefinitions([...originalDefinitions]);
      setFilterValues(revertedFilterValues);
      applyQueryState(
        [...originalDefinitions],
        revertedFilterValues,
        appliedNamespaceId,
      );
      setIsEditMode(false);
      setDashboardReloadVersion((prev) => prev + 1);
    };

    const removeWidget = (id: string) => {
      const nextLayout = layout.filter((item) => item.i !== id);
      const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
      const syncedLayout = syncLayoutFilterBindings(nextLayout, nextDefinitions);
      const nextFilterValues = syncFilterValuesWithDefinitions(
        nextDefinitions,
        filterValues,
      );
      const nextAppliedValues = syncFilterValuesWithDefinitions(
        nextDefinitions,
        appliedFilterValues,
      );

      setLayout(syncedLayout);
      void syncDashboardCanvasResources(syncedLayout).then(() => {
        syncFilterStateAfterLayoutChange(
          nextDefinitions,
          nextFilterValues,
          nextAppliedValues,
        );
      });
    };

    const handleEdit = (id: string) => {
      const item = layout.find((i) => i.i === id);
      setCurrentConfigItem(item);
      setIsNewComponentConfig(false);
      setConfigDrawerVisible(true);
    };

    const handleOpenConfig = (item: DatasourceItem) => {
      const configItem = {
        i: '',
        x: 0,
        y: 0,
        w: 4,
        h: 3,
        name: item.name,
        description: item.desc,
        valueConfig: {
          dataSource: item?.id,
          chartType: '',
          dataSourceParams: [],
        },
      };
      setCurrentConfigItem(configItem);
      setIsNewComponentConfig(true);
      setConfigDrawerVisible(true);
    };

    const handleConfigConfirm = (values: WidgetConfig) => {
      if (isNewComponentConfig && currentConfigItem) {
        handleAddComponent(values);
      } else {
        const editedWidgetId = currentConfigItem?.i;
        const nextLayout = layout.map((item) => {
          if (item.i === editedWidgetId) {
            return {
              ...item,
              name: values.name,
              description: values.description,
              valueConfig: {
                ...item.valueConfig,
                dataSource: values.dataSource,
                chartType: values.chartType,
                dataSourceParams: values.dataSourceParams,
                tableConfig: values.tableConfig,
                filterBindings: values.filterBindings,
                selectedFields: values.selectedFields,
                topNLabelField: values.topNLabelField,
                topNValueField: values.topNValueField,
                unit: values.unit,
                conversionFactor: values.conversionFactor,
                decimalPlaces: values.decimalPlaces,
                thresholdColors: values.thresholdColors,
                compare: values.compare,
              },
            };
          }
          return item;
        });

        const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
        const syncedLayout = syncLayoutFilterBindings(nextLayout, nextDefinitions);
        const nextFilterValues = syncFilterValuesWithDefinitions(nextDefinitions, filterValues);
        const nextAppliedValues = syncFilterValuesWithDefinitions(
          nextDefinitions,
          appliedFilterValues,
        );

        setLayout(syncedLayout);
        void syncDashboardCanvasResources(syncedLayout).then(() => {
          syncFilterStateAfterLayoutChange(
            nextDefinitions,
            nextFilterValues,
            nextAppliedValues,
          );
        });
        
        // Only refresh the edited widget, not all widgets
        if (editedWidgetId) {
          setWidgetReloadVersions((prev) => ({
            ...prev,
            [editedWidgetId]: (prev[editedWidgetId] || 0) + 1,
          }));
        }
      }
      setConfigDrawerVisible(false);
      setCurrentConfigItem(undefined);
      setIsNewComponentConfig(false);
    };

    const handleConfigClose = () => {
      setConfigDrawerVisible(false);
      setCurrentConfigItem(undefined);
      setIsNewComponentConfig(false);
    };

    const handleFilterSearch = (values: Record<string, FilterValue>) => {
      const namespaceChanged = namespaceDraftId !== appliedNamespaceId;

      setFilterValues(values);
      applyQueryState(definitions, values, namespaceDraftId);

      setFilterSearchVersion((prev) => prev + 1);
      if (namespaceChanged) {
        setNamespaceSearchVersion((prev) => prev + 1);
      }
    };

    const handleFilterReset = (values: Record<string, FilterValue>) => {
      handleFilterSearch(values);
    };

    const handleFilterConfigConfirm = (
      newDefinitions: UnifiedFilterDefinition[],
    ) => {
      updateDefinitions(newDefinitions);
      const updatedValues = syncFilterValuesWithDefinitions(newDefinitions, filterValues);
      setFilterValues(updatedValues);
    };

    const handleDelete = (id: string) => {
      Modal.confirm({
        title: t('common.delConfirm'),
        content: t('common.delConfirmCxt'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        okButtonProps: { danger: true },
        centered: true,
        onOk: async () => {
          try {
            removeWidget(id);
          } catch {
            console.error(t('common.operateFailed'));
          }
        },
      });
    };

    return (
      <div
        className="h-full flex-1 overflow-auto flex flex-col"
        style={{
          backgroundColor: isDarkTheme ? 'var(--color-fill-1)' : '#f7f8fa',
        }}
      >
        <div
          ref={exportRef}
          className="flex-1 min-h-0 flex flex-col"
          data-export-expand="true"
        >
          <div
            className="w-full mb-2 flex items-center justify-between bg-(--color-bg-1) px-4 py-2 border-b border-(--color-border-2)"
          >
            <div className="flex-1 mr-8">
              {selectedDashboard && (
                <div>
                  <h2 className="text-base leading-6 font-semibold text-(--color-text-1)">
                    {selectedDashboard.name}
                    {selectedDashboard.is_build_in && (
                      <Tag
                        color="blue"
                        className="ml-2 text-xs align-middle rounded-full! px-2! py-0.5!"
                      >
                        {t('common.builtIn')}
                      </Tag>
                    )}
                  </h2>
                  {selectedDashboard.desc && (
                    <p className="text-xs leading-4 text-(--color-text-3) mt-0.5">
                      {selectedDashboard.desc}
                    </p>
                  )}
                </div>
              )}
            </div>
            {/* 右侧：工具栏 */}
            <div
              className="flex items-center gap-1.5"
              data-export-hidden="true"
            >
              <Tooltip title={t('common.refresh')}>
                <Button
                  type="text"
                  icon={<ReloadOutlined style={{ fontSize: 16 }} />}
                  onClick={handleRefresh}
                  className="rounded-full!"
                />
              </Tooltip>

              {!isEditMode && (
                <Tooltip title={t('dashboard.exportPdf')}>
                  <Button
                    type="text"
                    icon={<DownloadOutlined style={{ fontSize: 16 }} />}
                    loading={exporting}
                    onClick={handleExportPdf}
                    className="rounded-full!"
                  />
                </Tooltip>
              )}

              {isEditMode && (
                <>
                  <PermissionWrapper requiredPermissions={['EditChart']}>
                    <Tooltip title={t('dashboard.configUnifiedFilterFields')}>
                      <Button
                        type="text"
                        icon={<SettingOutlined style={{ fontSize: 16 }} />}
                        onClick={() => setFilterConfigModalVisible(true)}
                        className="rounded-full!"
                      />
                    </Tooltip>
                  </PermissionWrapper>
                  <PermissionWrapper requiredPermissions={['EditChart']}>
                    <Button
                      type="default"
                      icon={<PlusOutlined />}
                      onClick={openAddModal}
                      className="rounded-full!"
                      style={{
                        borderColor: chartTheme.panelBorderColor,
                        color: 'var(--color-text-1)',
                        background: chartTheme.panelBg,
                      }}
                    >
                      {t('dashboard.addView')}
                    </Button>
                  </PermissionWrapper>
                </>
              )}

              <div>
                <PermissionWrapper requiredPermissions={['EditChart']}>
                  {!isEditMode ? (
                    <Tooltip title={t('common.edit')}>
                      <Button
                        type="text"
                        aria-label={t('common.edit')}
                        icon={<EditOutlined aria-hidden="true" style={{ fontSize: 16 }} />}
                        disabled={
                          !selectedDashboard?.data_id ||
                          selectedDashboard?.is_build_in
                        }
                        onClick={toggleEditMode}
                        className="rounded-full!"
                      />
                    </Tooltip>
                  ) : (
                    <div className="flex items-center gap-2 ml-4">
                      <Button
                        disabled={!selectedDashboard?.data_id}
                        onClick={handleCancelEdit}
                        className="rounded-full!"
                      >
                        {t('common.cancel')}
                      </Button>
                      <Button
                        type="primary"
                        loading={saving}
                        disabled={!selectedDashboard?.data_id}
                        onClick={handleSave}
                        className="rounded-full!"
                      >
                        {t('common.save')}
                      </Button>
                    </div>
                  )}
                </PermissionWrapper>
              </div>
            </div>
          </div>

          <div
            className="flex-1 overflow-hidden flex flex-col"
            style={{
              backgroundColor: isDarkTheme ? 'var(--color-bg-1)' : '#f7f8fa',
            }}
            data-export-expand="true"
          >
            {(definitions.length > 0 || namespaceSelectorElement) && (
              <div className="shrink-0">
                <UnifiedFilterBar
                  definitions={definitions}
                  values={filterValues}
                  onSearch={handleFilterSearch}
                  onReset={handleFilterReset}
                  prefixContent={namespaceSelectorElement}
                />
              </div>
            )}
            <div className="flex-1 overflow-auto" data-export-expand="true">
              {(() => {
                if (loading) {
                  return (
                    <div className="h-full flex items-center justify-center">
                      <Spin size="large" />
                    </div>
                  );
                }

                if (!layout.length) {
                  return (
                    <div className="h-full flex flex-col items-center justify-center">
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                          <span className="text-(--color-text-2)">
                            {t('dashboard.addView')}
                          </span>
                        }
                      >
                        <PermissionWrapper requiredPermissions={['EditChart']}>
                          <Button
                            type="primary"
                            icon={<PlusOutlined aria-hidden="true" />}
                            onClick={openAddModal}
                            disabled={selectedDashboard?.is_build_in}
                          >
                            {t('dashboard.addView')}
                          </Button>
                        </PermissionWrapper>
                      </Empty>
                    </div>
                  );
                }
                return (
                  <ResponsiveGridLayout
                    className="layout w-full flex-1"
                    layout={layout}
                    onLayoutChange={onLayoutChange}
                    cols={12}
                    rowHeight={40}
                    margin={[8, 8]}
                    containerPadding={[10, 4]}
                    draggableCancel=".no-drag, .widget-body"
                    isDraggable={isEditMode}
                    isResizable={isEditMode}
                  >
                    {layout.map((item) => {
                      const isTableWidget =
                        item.valueConfig?.chartType === 'table';
                      const menu = (
                        <Menu>
                          <Menu.Item
                            key="edit"
                            onClick={() => handleEdit(item.i)}
                          >
                            {t('common.edit')}
                          </Menu.Item>
                          <Menu.Item
                            key="delete"
                            onClick={() => handleDelete(item.i)}
                          >
                            {t('common.delete')}
                          </Menu.Item>
                        </Menu>
                      );

                      return (
                        <div
                          key={item.i}
                          className="widget rounded-lg overflow-hidden p-3 flex flex-col"
                          style={{
                            backgroundColor: chartTheme.panelBg,
                            border: `1px solid ${chartTheme.panelBorderColor}`,
                          }}
                        >
                          <div className="widget-header mb-2 flex justify-between items-start gap-2">
                            <div className="flex-1 min-w-0">
                              <h4 className="truncate text-[14px] font-medium leading-5 text-(--color-text-2)">
                                {item.name}
                              </h4>
                              {item.description?.trim() && (
                                <p className="mt-0.5 text-[11px] leading-4 text-(--color-text-3) wrap-break-word whitespace-normal">
                                  {item.description}
                                </p>
                              )}
                            </div>
                            {isEditMode && (
                              <Dropdown overlay={menu} trigger={['click']}>
                                <button
                                  type="button"
                                  aria-label={t('common.more')}
                                  className="no-drag text-(--color-text-2) hover:text-(--color-text-1) transition-colors cursor-pointer"
                                >
                                  <MoreOutlined aria-hidden="true" style={{ fontSize: '18px' }} />
                                </button>
                              </Dropdown>
                            )}
                          </div>
                          <div
                            className={`widget-body flex-1 h-full`}
                            style={{
                              overflow: isTableWidget ? 'visible' : 'hidden',
                            }}
                          >
                            <WidgetWrapper
                              widgetId={item.i}
                              key={item.i}
                              chartType={item.valueConfig?.chartType}
                              config={item.valueConfig}
                              filterSearchVersion={filterSearchVersion}
                              namespaceSearchVersion={namespaceSearchVersion}
                              reloadVersion={`${dashboardReloadVersion}:${widgetReloadVersions[item.i] || 0}`}
                              dataSource={dataSourceManager.findDataSource(
                                item.valueConfig?.dataSource,
                              )}
                              unifiedFilterValues={appliedFilterValues}
                              filterDefinitions={appliedFilterDefinitions}
                              builtinNamespaceId={appliedNamespaceId}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </ResponsiveGridLayout>
                );
              })()}
            </div>
          </div>
        </div>

        <ViewSelector
          visible={addModalVisible}
          onCancel={() => setAddModalVisible(false)}
          onOpenConfig={handleOpenConfig}
        />
        <ViewConfig
          open={configDrawerVisible}
          item={currentConfigItem as LayoutItem}
          onConfirm={handleConfigConfirm}
          onClose={handleConfigClose}
          builtinNamespaceId={namespaceDraftId}
          dataSourceManager={dataSourceManager}
          filterDefinitions={definitions}
          unifiedFilterValues={filterValues}
        />
        <UnifiedFilterConfigModal
          open={filterConfigModalVisible}
          onCancel={() => setFilterConfigModalVisible(false)}
          onConfirm={handleFilterConfigConfirm}
          definitions={definitions}
          layoutItems={layout}
          dataSources={dataSourceManager.dataSources}
        />
      </div>
    );
  }
);

Dashboard.displayName = 'Dashboard';

export default Dashboard;
