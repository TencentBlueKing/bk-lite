import {
  useState,
  useEffect,
  useMemo,
  useRef,
  forwardRef,
  useImperativeHandle,
  useCallback,
} from 'react';
import { v4 as uuidv4 } from 'uuid';
import ViewSelector from '@/app/ops-analysis/components/widgetSelector';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import { mergeSanitizedWidgetValueConfig, omitForeignChartTypeFields } from '@/app/ops-analysis/components/widgetConfig/utils/submitConfig';
import DashboardCanvas from './components/dashboardCanvas';
import DashboardToolbar from './components/dashboardToolbar';
import DashboardSubscriptionModal from '@/app/ops-analysis/components/dashboardSubscriptionModal';
import ViewWorkspace from '../components/viewWorkspace';
import { Input, Modal, message, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useCanvasResources } from '@/app/ops-analysis/hooks/useCanvasResources';
import { useCanvasShareAction } from '@/app/ops-analysis/hooks/useCanvasShareAction';
import {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
  OtherConfig,
  LayoutItem,
  WidgetConfig,
  UnifiedFilterDefinition,
  FilterValue,
  ComponentSelectorConfigItem,
} from '@/app/ops-analysis/types/dashBoard';
import { DirItem } from '@/app/ops-analysis/types';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import { useUnifiedFilter } from '@/app/ops-analysis/hooks/useUnifiedFilter';
import { useDashBoardApi } from '@/app/ops-analysis/api/dashBoard';
import { useDirectoryApi } from '@/app/ops-analysis/api';
import useBtnPermissions from '@/hooks/usePermissions';
import { useCanvasPeriodicRefresh } from '@/app/ops-analysis/hooks/useCanvasPeriodicRefresh';
import { canPersistCanvasRefreshInterval, normalizeCanvasRefreshInterval } from '@/app/ops-analysis/utils/canvasRefreshInterval';
import type { CanvasRuntimeRefreshCause } from '@/app/ops-analysis/utils/canvasRefreshTimer';
import {
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
} from '@/app/ops-analysis/components/unifiedFilter';
import { collectNamespaceOptions } from '@/app/ops-analysis/utils/namespaceFilter';
import {
  collectDashboardDataSourceIds,
  collectDashboardNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import { exportDashboardToPdf } from '@/app/ops-analysis/utils/exportPdf';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import 'react-resizable/css/styles.css';
import { useSession } from 'next-auth/react';
import { useDashboardLayoutSync } from './hooks/useDashboardLayoutSync';
import {
  deserializeDashboardGridStackLayout,
  serializeDashboardGridStackLayout,
} from '@/app/ops-analysis/utils/dashboardGridStack';
import {
  buildDashboardGroupStorageKey,
  bumpDashboardGroupWidgetReloadVersions,
  getDashboardGroupWidgetIds,
  insertDashboardWidgetIntoGroup,
  isDashboardGroupItem,
  isDashboardWidgetItem,
  removeDashboardGroupHeader,
  sanitizeCollapsedGroups,
} from '@/app/ops-analysis/utils/dashboardGroups';
import {
  buildDashboardRenderSignal,
  emitDashboardRenderSignal,
  type DashboardWidgetRenderResult,
  type DashboardRenderSignal,
} from '@/app/ops-analysis/renderContract';
import { prepareDashboardPrintLayout } from '@/app/ops-analysis/utils/prepareDashboardPrintLayout';
import { useCanvasDraft } from '@/app/ops-analysis/hooks/useCanvasDraft';
import {
  restoreDraftRefreshInterval,
  toCanvasDraftResourceId,
  type CanvasDraftPayload,
} from '@/app/ops-analysis/api/canvasDraft';
import { bindCanvasDraftControls } from '@/app/ops-analysis/components/canvasDraftControls';
import { normalizeStoredFilterState, buildFilterConfigConfirmSnapshot } from '@/app/ops-analysis/utils/unifiedFilterState';
import { copyDashboardWidget } from '@/app/ops-analysis/utils/widgetCopy';
import {
  migrateFilterBindings,
  migrateParamItemsFromStringList,
  logStringParamMigrationWarnings,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

interface DashboardProps {
  selectedDashboard?: DirItem | null;
  shareMode?: boolean;
  shareSessionId?: string;
  getDashboardDetailOverride?: (id: string | number) => Promise<any>;
  renderMode?: boolean;
  renderFilterValues?: Record<string, FilterValue>;
  renderDataSourceIds?: number[];
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  ({
    selectedDashboard,
    shareMode = false,
    getDashboardDetailOverride,
    renderMode = false,
    renderFilterValues,
    renderDataSourceIds,
  }, ref) => {
    const { t } = useTranslation();
    const { data: session } = useSession();
    const themeName = renderMode ? 'light' : resolveOpsChartThemeName();
    const chartTheme = getOpsChartTheme(themeName);
    const isDarkTheme = themeName === 'dark';
    const { getDashboardDetail, saveDashboard } = useDashBoardApi();
    const { updateItem } = useDirectoryApi();
    const { hasPermission } = useBtnPermissions();
    const dataSourceManager = useDataSourceManager();
    const { namespaceList, loadCanvasNamespaces } = useOpsAnalysis();
    const { syncCanvasResources } = useCanvasResources();
    const [isEditMode, setIsEditMode] = useState(false);
    const [addModalVisible, setAddModalVisible] = useState(false);
    const [layout, setLayout] = useState<DashboardLayoutItem[]>([]);
    const [originalLayout, setOriginalLayout] = useState<DashboardLayoutItem[]>(
      [],
    );
    const [collapsedGroups, setCollapsedGroups] = useState<
      Record<string, true>
    >({});
    const [groupNameModalVisible, setGroupNameModalVisible] = useState(false);
    const [groupNameDraft, setGroupNameDraft] = useState('');
    const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
    const [isCreatingGroupName, setIsCreatingGroupName] = useState(false);
    const [pendingNewWidgetGroupId, setPendingNewWidgetGroupId] = useState<
      string | null
    >(null);
    const [configDrawerVisible, setConfigDrawerVisible] = useState(false);
    const [currentConfigItem, setCurrentConfigItem] = useState<LayoutItem>();
    const [isNewComponentConfig, setIsNewComponentConfig] = useState(false);
    const [dashboardReloadVersion, setDashboardReloadVersion] = useState(0);
    const [refreshCause, setRefreshCause] =
      useState<CanvasRuntimeRefreshCause>('initial');
    const [savedRefreshInterval, setSavedRefreshInterval] = useState(0);
    const [widgetReloadVersions, setWidgetReloadVersions] = useState<
      Record<string, number>
    >({});
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(false);
    const [otherConfig, setOtherConfig] = useState<OtherConfig>({});
    const [originalOtherConfig, setOriginalOtherConfig] = useState<OtherConfig>(
      {},
    );
    const [filterConfigModalVisible, setFilterConfigModalVisible] =
      useState(false);
    const [subscriptionModalVisible, setSubscriptionModalVisible] =
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
    const canvasScrollRef = useRef<HTMLDivElement>(null);
    const getDashboardDetailRef = useRef(getDashboardDetailOverride ?? getDashboardDetail);
    const collapsedGroupsHydratedKeyRef = useRef<string | null>(null);
    const skipCollapsedGroupsPersistRef = useRef(false);
    const [collapsedGroupsLayoutReadyId, setCollapsedGroupsLayoutReadyId] =
      useState<number | string | null>(null);
    const { shareLoading, openShare } = useCanvasShareAction('dashboard');
    const [exporting, setExporting] = useState(false);
    const renderResultsRef = useRef(
      new Map<string, DashboardWidgetRenderResult>(),
    );
    const emittedRenderSignalRef = useRef(false);
    const resumeEditModeAfterFullscreenRef = useRef(false);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();

    useEffect(() => {
      getDashboardDetailRef.current = getDashboardDetailOverride ?? getDashboardDetail;
    }, [getDashboardDetail, getDashboardDetailOverride]);

    const {
      definitions,
      filterValues,
      setFilterValues,
      updateDefinitions,
      setDefinitions,
    } = useUnifiedFilter();
    const [originalDefinitions, setOriginalDefinitions] = useState<
      UnifiedFilterDefinition[]
    >([]);

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

    const syncDashboardCanvasResources = useCallback(
      async (nextLayout: DashboardLayoutItem[]) => {
        const nextWidgetLayout = nextLayout.filter(isDashboardWidgetItem);

        return syncCanvasResources({
          source: nextWidgetLayout,
          getDataSourceIds: (layout) => Array.from(new Set([
            ...collectDashboardDataSourceIds(layout),
            ...(renderDataSourceIds || []),
          ])),
          getNamespaceIds: collectDashboardNamespaceIds,
        });
      },
      [renderDataSourceIds, syncCanvasResources],
    );

    const {
      buildFiltersFromLayout,
      resolveLayoutNamespaceId,
      syncFilterStateAfterLayoutChange,
      syncFilterValuesWithDefinitions,
      syncLayoutFilterBindings,
    } = useDashboardLayoutSync({
      dataSources: dataSourceManager.dataSources,
      namespaceDraftId,
      appliedNamespaceId,
      applyQueryState,
      setDefinitions,
      setFilterValues,
    });

    const dashboardDraftResourceId = toCanvasDraftResourceId(
      selectedDashboard?.data_id,
    );
    const getDashboardDraftPayload = useCallback(
      (): CanvasDraftPayload => ({
        name: selectedDashboard?.name,
        desc: selectedDashboard?.desc || '',
        view_sets: serializeDashboardGridStackLayout(layout),
        filters: definitions,
        other: otherConfig,
        refresh_interval: savedRefreshInterval,
      }),
      [
        definitions,
        layout,
        otherConfig,
        savedRefreshInterval,
        selectedDashboard?.desc,
        selectedDashboard?.name,
      ],
    );
    const applyDashboardDraftPayload = useCallback(
      (payload: CanvasDraftPayload) => {
        const nextLayout = deserializeDashboardGridStackLayout(payload.view_sets);
        const loadedDefinitions: UnifiedFilterDefinition[] = Array.isArray(
          payload.filters,
        )
          ? payload.filters
          : [];
        const nextValues = syncFilterValuesWithDefinitions(loadedDefinitions, {});

        restoreDraftRefreshInterval(payload, setSavedRefreshInterval);
        setLayout(nextLayout);
        setOtherConfig((payload.other as OtherConfig) || {});
        setDefinitions(loadedDefinitions);
        setFilterValues(nextValues);
        applyQueryState(loadedDefinitions, nextValues, appliedNamespaceId);
        void syncDashboardCanvasResources(nextLayout);
      },
      [
        appliedNamespaceId,
        applyQueryState,
        setDefinitions,
        setFilterValues,
        setSavedRefreshInterval,
        syncDashboardCanvasResources,
        syncFilterValuesWithDefinitions,
      ],
    );
    const dashboardDraft = useCanvasDraft({
      resourceType: 'dashboard',
      resourceId: dashboardDraftResourceId,
      enabled: Boolean(
        isEditMode &&
          !shareMode &&
          !renderMode &&
          dashboardDraftResourceId &&
          !selectedDashboard?.is_build_in,
      ),
      getPayload: getDashboardDraftPayload,
      applyPayload: applyDashboardDraftPayload,
    });

    const widgetLayoutItems = useMemo(
      () => layout.filter(isDashboardWidgetItem),
      [layout],
    );

    const emitPreparedRenderSignal = useCallback(
      async (signal: DashboardRenderSignal) => {
        if (emittedRenderSignalRef.current) return;
        emittedRenderSignalRef.current = true;
        if (signal.type === 'report-ready') {
          try {
            await prepareDashboardPrintLayout();
          } catch (error) {
            emitDashboardRenderSignal({
              type: 'report-failed',
              dashboardId: signal.dashboardId,
              widgets: signal.widgets,
              error:
                error instanceof Error
                  ? error.message
                  : 'Dashboard print preparation failed',
            });
            return;
          }
        }
        emitDashboardRenderSignal(signal);
      },
      [],
    );

    const handleWidgetRenderStatus = useCallback(
      (result: DashboardWidgetRenderResult) => {
        if (!renderMode || emittedRenderSignalRef.current) return;
        renderResultsRef.current.set(result.widgetId, result);
        const signal = buildDashboardRenderSignal(
          selectedDashboard?.data_id || 'unknown',
          widgetLayoutItems.map((item) => item.i),
          renderResultsRef.current,
        );
        if (signal) {
          void emitPreparedRenderSignal(signal);
        }
      },
      [
        emitPreparedRenderSignal,
        renderMode,
        selectedDashboard?.data_id,
        widgetLayoutItems,
      ],
    );

    const groupIds = useMemo(
      () => new Set(layout.filter(isDashboardGroupItem).map((item) => item.i)),
      [layout],
    );

    const collapsedGroupStorageKey = useMemo(() => {
      const username = (session?.user as { username?: string } | undefined)
        ?.username;
      if (!username || !selectedDashboard?.data_id) {
        return null;
      }

      return buildDashboardGroupStorageKey(username, selectedDashboard.data_id);
    }, [selectedDashboard?.data_id, session?.user]);

    const namespaceOptions = useMemo(() => {
      return collectNamespaceOptions(
        widgetLayoutItems,
        dataSourceManager.dataSources,
        namespaceList,
      );
    }, [widgetLayoutItems, dataSourceManager.dataSources, namespaceList]);

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
          setCollapsedGroupsLayoutReadyId(null);
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
          const nextLayout = deserializeDashboardGridStackLayout(
            dashboardData.view_sets,
          ).map((item) => {
            if (!isDashboardWidgetItem(item) || !item.valueConfig) {
              return item;
            }
            const valueConfig = item.valueConfig;
            return {
              ...item,
              valueConfig: {
                ...valueConfig,
                ...(valueConfig.filterBindings
                  ? {
                    filterBindings: migrateFilterBindings(
                      valueConfig.filterBindings,
                    ),
                  }
                  : {}),
                ...(valueConfig.dataSourceParams
                  ? (() => {
                    const migratedParams = migrateParamItemsFromStringList(
                      valueConfig.dataSourceParams,
                    );
                    logStringParamMigrationWarnings(migratedParams.warnings, {
                      canvasId: selectedDashboard.data_id,
                    });
                    return { dataSourceParams: migratedParams.params };
                  })()
                  : {}),
              },
            };
          });
          await syncDashboardCanvasResources(nextLayout);
          if (nextLayout.length) {
            setLayout(nextLayout);
            setOriginalLayout([...nextLayout]);
          } else {
            setLayout([]);
            setOriginalLayout([]);
            void loadCanvasNamespaces([]);
          }

          setCollapsedGroupsLayoutReadyId(selectedDashboard.data_id);

          const savedOtherConfig = dashboardData.other || {};
          setOtherConfig(savedOtherConfig);
          setOriginalOtherConfig({ ...savedOtherConfig });
          setSavedRefreshInterval(
            normalizeCanvasRefreshInterval(dashboardData.refresh_interval),
          );

          // Handle both legacy (unifiedFilters) and new (direct array) format
          const rawFilters = dashboardData.filters;
          const { definitions: loadedDefinitions, values: migratedValues } =
            normalizeStoredFilterState(
              rawFilters,
              renderMode ? (renderFilterValues ?? {}) : {},
              { canvasId: selectedDashboard.data_id },
            );

          const initialValues = syncFilterValuesWithDefinitions(
            loadedDefinitions,
            migratedValues,
          );

          setDefinitions(loadedDefinitions);
          setFilterValues(initialValues);
          setAppliedFilterDefinitions(loadedDefinitions);
          setAppliedFilterValues(initialValues);
          setOriginalDefinitions([...loadedDefinitions]);
        } catch (error) {
          console.error('加载仪表盘数据失败:', error);
          setCollapsedGroupsLayoutReadyId(selectedDashboard.data_id);
          setLayout([]);
          setOriginalLayout([]);
          setOtherConfig({});
          setOriginalOtherConfig({});
          setDefinitions([]);
          setFilterValues({});
          setAppliedFilterDefinitions([]);
          setAppliedFilterValues({});
          setOriginalDefinitions([]);
          if (renderMode && !emittedRenderSignalRef.current) {
            emittedRenderSignalRef.current = true;
            emitDashboardRenderSignal({
              type: 'report-failed',
              dashboardId: String(selectedDashboard.data_id),
              widgets: [],
              error:
                error instanceof Error
                  ? error.message
                  : 'Dashboard layout load failed',
            });
          }
        } finally {
          setLoading(false);
        }
      };
      loadDashboardData();
    }, [
      selectedDashboard?.data_id,
      loadCanvasNamespaces,
      syncDashboardCanvasResources,
      renderMode,
      renderFilterValues,
    ]);

    // 监听 selectedDashboard 的变化，重置状态
    useEffect(() => {
      collapsedGroupsHydratedKeyRef.current = null;
      skipCollapsedGroupsPersistRef.current = false;
      setCollapsedGroupsLayoutReadyId(null);
      setIsEditMode(false);
      setAddModalVisible(false);
      setConfigDrawerVisible(false);
      setCurrentConfigItem(undefined);
      setIsNewComponentConfig(false);
      setGroupNameModalVisible(false);
      setGroupNameDraft('');
      setEditingGroupId(null);
      setIsCreatingGroupName(false);
      setSaving(false);
      setDashboardReloadVersion(0);
      setRefreshCause('initial');
      setSavedRefreshInterval(0);
      setFilterSearchVersion(0);
      setNamespaceSearchVersion(0);
      setWidgetReloadVersions({});
      setAppliedFilterDefinitions([]);
      setAppliedFilterValues({});
      setNamespaceDraftId(undefined);
      setAppliedNamespaceId(undefined);
      setPendingNewWidgetGroupId(null);
    }, [selectedDashboard?.data_id]);

    useEffect(() => {
      const selectedDashboardId = selectedDashboard?.data_id;

      if (!collapsedGroupStorageKey) {
        collapsedGroupsHydratedKeyRef.current = null;
        setCollapsedGroups({});
        return;
      }

      if (
        loading ||
        collapsedGroupsLayoutReadyId !== selectedDashboardId ||
        collapsedGroupsHydratedKeyRef.current === collapsedGroupStorageKey
      ) {
        return;
      }

      let parsedValue: unknown = {};

      try {
        const rawValue = window.localStorage.getItem(collapsedGroupStorageKey);
        parsedValue = rawValue ? JSON.parse(rawValue) : {};
      } catch {
        parsedValue = {};
      }

      collapsedGroupsHydratedKeyRef.current = collapsedGroupStorageKey;
      skipCollapsedGroupsPersistRef.current = true;
      setCollapsedGroups(sanitizeCollapsedGroups(parsedValue, groupIds));
    }, [
      collapsedGroupStorageKey,
      collapsedGroupsLayoutReadyId,
      groupIds,
      loading,
      selectedDashboard?.data_id,
    ]);

    useEffect(() => {
      const selectedDashboardId = selectedDashboard?.data_id;

      if (
        !collapsedGroupStorageKey ||
        loading ||
        collapsedGroupsLayoutReadyId !== selectedDashboardId ||
        collapsedGroupsHydratedKeyRef.current !== collapsedGroupStorageKey
      ) {
        return;
      }

      if (skipCollapsedGroupsPersistRef.current) {
        skipCollapsedGroupsPersistRef.current = false;
        return;
      }

      const sanitized = sanitizeCollapsedGroups(collapsedGroups, groupIds);

      if (Object.keys(sanitized).length === 0) {
        window.localStorage.removeItem(collapsedGroupStorageKey);
        return;
      }

      window.localStorage.setItem(
        collapsedGroupStorageKey,
        JSON.stringify(sanitized),
      );
    }, [
      collapsedGroupStorageKey,
      collapsedGroups,
      collapsedGroupsLayoutReadyId,
      groupIds,
      loading,
      selectedDashboard?.data_id,
    ]);

    const toggleCollapsedGroup = useCallback((groupId: string) => {
      const isExpanding = Boolean(collapsedGroups[groupId]);

      setCollapsedGroups((previous) => {
        if (previous[groupId]) {
          const next = { ...previous };
          delete next[groupId];
          return next;
        }

        return { ...previous, [groupId]: true };
      });

      if (isExpanding) {
        setWidgetReloadVersions((versions) =>
          bumpDashboardGroupWidgetReloadVersions(layout, groupId, versions),
        );
      }
    }, [collapsedGroups, layout]);

    const openAddModal = (groupId?: string) => {
      setIsEditMode(true);
      setPendingNewWidgetGroupId(groupId ?? null);
      setAddModalVisible(true);
    };

    const closeAddModal = () => {
      setAddModalVisible(false);
      setPendingNewWidgetGroupId(null);
    };

    const closeGroupNameModal = useCallback(() => {
      setGroupNameModalVisible(false);
      setGroupNameDraft('');
      setEditingGroupId(null);
      setIsCreatingGroupName(false);
    }, []);

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
          JSON.stringify(definitions) !== JSON.stringify(originalDefinitions);
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
      setRefreshCause('manual');
      setDashboardReloadVersion((prev) => prev + 1);
    };

    const handlePeriodicRefresh = useCallback(
      (cause: CanvasRuntimeRefreshCause = 'periodic') => {
        setRefreshCause(cause);
        setDashboardReloadVersion((prev) => prev + 1);
      },
      [],
    );

    const canPersistRefreshInterval = canPersistCanvasRefreshInterval({
      shareMode,
      isBuiltIn: Boolean(selectedDashboard?.is_build_in),
      hasEditPermission: hasPermission(['EditChart']),
    });

    const { effectiveRefreshInterval, handleFrequencyChange } =
      useCanvasPeriodicRefresh({
        canvasId: selectedDashboard?.data_id,
        savedInterval: savedRefreshInterval,
        canPersist: canPersistRefreshInterval,
        enabled: !renderMode && !isEditMode,
        patchRefreshInterval: async (interval) => {
          if (!selectedDashboard?.data_id) {
            return;
          }
          await updateItem('dashboard', selectedDashboard.data_id, {
            refresh_interval: interval,
          });
        },
        onPeriodicRefresh: handlePeriodicRefresh,
        onSavedIntervalChange: setSavedRefreshInterval,
      });

    const handleExportPdf = useCallback(async () => {
      if (!exportRef.current) return;
      setExporting(true);
      try {
        await exportDashboardToPdf(
          exportRef.current,
          selectedDashboard?.name || 'dashboard',
        );
        message.success(t('dashboard.exportPdfSuccess'));
      } catch (err) {
        console.error('Export PDF failed:', err);
        message.error(t('dashboard.exportPdfFailed'));
      } finally {
        setExporting(false);
      }
    }, [selectedDashboard?.name, t]);

    const handleLayoutCommit = useCallback(
      (newLayout: DashboardLayoutItem[]) => {
        if (!isEditMode) {
          return;
        }

        setLayout((prevLayout) => {
          if (JSON.stringify(prevLayout) === JSON.stringify(newLayout)) {
            return prevLayout;
          }

          return newLayout;
        });
      },
      [isEditMode],
    );

    const handleTopologyLayoutChange = useCallback(
      (
        widgetId: string,
        nextTopology: NonNullable<
          NonNullable<DashboardWidgetLayoutItem['valueConfig']>['networkStatusTopology']
        >,
      ) => {
        if (!isEditMode || shareMode) return;
        setLayout((prevLayout) =>
          prevLayout.map((item) => {
            if (item.i !== widgetId || !isDashboardWidgetItem(item)) {
              return item;
            }
            return {
              ...item,
              valueConfig: {
                ...item.valueConfig,
                networkStatusTopology: nextTopology,
              },
            };
          }),
        );
      },
      [isEditMode, shareMode],
    );

    const handleAddComponent = (config: WidgetConfig, draftItem: LayoutItem) => {
      const nextUngroupedY = layout.reduce(
        (maxY, item) => Math.max(maxY, item.y + item.h),
        0,
      );

      const newWidget: DashboardWidgetLayoutItem = {
        i: uuidv4(),
        x: 0,
        y: nextUngroupedY,
        w: draftItem.w,
        h: draftItem.h,
        groupId: null,
        name: config.name,
        description: config.description,
        valueConfig: omitForeignChartTypeFields(
          {
            dataSource: config.dataSource,
            chartType: config.chartType,
            sceneWidgetType: config.sceneWidgetType,
            networkStatusTopology: config.networkStatusTopology,
            dataSourceParams: config.dataSourceParams || [],
            tableConfig: config.tableConfig,
            filterBindings: config.filterBindings,
            selectedFields: config.selectedFields,
            descriptionField: config.descriptionField,
            topNLabelField: config.topNLabelField,
            topNValueField: config.topNValueField,
            unit: config.unit,
            unitId: config.unitId,
            valueMappings: config.valueMappings,
            chartThemeMode: config.chartThemeMode,
            appearance: config.appearance,
            conversionFactor: config.conversionFactor,
            decimalPlaces: config.decimalPlaces,
            thresholdColors: config.thresholdColors,
            gaugeMin: config.gaugeMin,
            gaugeMax: config.gaugeMax,
            gaugeShape: config.gaugeShape,
            cardList: config.cardList,
            compare: config.compare,
            actions: config.actions,
          },
          config.chartType || '',
        ),
      };
      const nextLayout = pendingNewWidgetGroupId
        ? insertDashboardWidgetIntoGroup(
          layout,
          newWidget,
          pendingNewWidgetGroupId,
        )
        : [...layout, newWidget];
      const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
      const syncedLayout = syncLayoutFilterBindings(
        nextLayout,
        nextDefinitions,
      );
      const nextFilterValues = syncFilterValuesWithDefinitions(
        nextDefinitions,
        filterValues,
      );
      const nextAppliedValues = syncFilterValuesWithDefinitions(
        nextDefinitions,
        appliedFilterValues,
      );

      setLayout(syncedLayout);
      void syncDashboardCanvasResources(syncedLayout).then(
        (canvasDataSources) => {
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
          if (
            (shouldApplyNamespace ? nextNamespaceId : appliedNamespaceId) !==
            appliedNamespaceId
          ) {
            setNamespaceSearchVersion((prev) => prev + 1);
          }
          closeAddModal();
        },
      );
    };

    const handleSave = async () => {
      if (!selectedDashboard) {
        message.warning(t('dashboard.selectDashboardFirst'));
        return;
      }

      try {
        setSaving(true);
        const saveData = {
          name: selectedDashboard.name,
          desc: selectedDashboard.desc || '',
          filters: definitions,
          other: otherConfig,
          view_sets: serializeDashboardGridStackLayout(layout),
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

    useEffect(() => {
      if (isFullscreen || !resumeEditModeAfterFullscreenRef.current) {
        return;
      }

      resumeEditModeAfterFullscreenRef.current = false;
      setIsEditMode(true);
    }, [isFullscreen]);

    // 全屏切换只改 chrome 可见性，不 remount canvas；通知 GridStack/图表按新容器尺寸重算
    useEffect(() => {
      if (renderMode) return;
      const frameId = window.requestAnimationFrame(() => {
        window.dispatchEvent(new Event('resize'));
      });
      return () => window.cancelAnimationFrame(frameId);
    }, [isFullscreen, renderMode]);

    const handleFullscreenToggle = useCallback(() => {
      if (isFullscreen) {
        exitFullscreen();
        return;
      }

      resumeEditModeAfterFullscreenRef.current = isEditMode;
      if (isEditMode) {
        setIsEditMode(false);
      }
      enterFullscreen();
    }, [enterFullscreen, exitFullscreen, isEditMode, isFullscreen]);

    const handleCancelEdit = () => {
      const revertedFilterValues = syncFilterValuesWithDefinitions(
        originalDefinitions,
        appliedFilterValues,
      );

      setLayout([...originalLayout]);
      setOtherConfig({ ...originalOtherConfig });
      setDefinitions([...originalDefinitions]);
      setFilterValues(revertedFilterValues);
      applyQueryState(
        [...originalDefinitions],
        revertedFilterValues,
        appliedNamespaceId,
      );
      setIsEditMode(false);
      closeGroupNameModal();
    };

    const removeLayoutItems = (idsToRemove: Set<string>) => {
      const nextLayout = layout.filter((item) => !idsToRemove.has(item.i));
      const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
      const syncedLayout = syncLayoutFilterBindings(
        nextLayout,
        nextDefinitions,
      );
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

    const removeWidget = (id: string) => {
      removeLayoutItems(new Set([id]));
    };

    const handleAddGroup = () => {
      setIsCreatingGroupName(true);
      setEditingGroupId(null);
      setGroupNameDraft('');
      setGroupNameModalVisible(true);
    };

    const handleRenameGroup = (groupId: string) => {
      const groupItem = layout.find((item) => item.i === groupId);

      if (!groupItem || !isDashboardGroupItem(groupItem)) {
        return;
      }

      setEditingGroupId(groupItem.i);
      setIsCreatingGroupName(false);
      setGroupNameDraft(groupItem.name);
      setGroupNameModalVisible(true);
    };

    const handleGroupNameConfirm = () => {
      const nextName = groupNameDraft.trim();

      if (!nextName) {
        return;
      }

      if (isCreatingGroupName) {
        const nextY = layout.reduce(
          (maxY, item) => Math.max(maxY, item.y + item.h),
          0,
        );
        const newGroup: DashboardLayoutItem = {
          i: `group-${uuidv4()}`,
          itemType: 'group',
          x: 0,
          y: nextY,
          w: 12,
          h: 1,
          name: nextName,
        };

        setLayout((prevLayout) => [...prevLayout, newGroup]);
        closeGroupNameModal();
        return;
      }

      if (!editingGroupId) {
        return;
      }

      setLayout((prevLayout) =>
        prevLayout.map((item) =>
          item.i === editingGroupId && isDashboardGroupItem(item)
            ? { ...item, name: nextName }
            : item,
        ),
      );
      closeGroupNameModal();
    };

    const handleRemoveGroup = (groupId: string) => {
      Modal.confirm({
        title: t('dashboard.unGroup'),
        content: t('dashboard.unGroupConfirm'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: async () => {
          const nextLayout = removeDashboardGroupHeader(layout, groupId);
          const nextDefinitions = buildFiltersFromLayout(
            nextLayout,
            definitions,
          );
          const syncedLayout = syncLayoutFilterBindings(
            nextLayout,
            nextDefinitions,
          );
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

          setCollapsedGroups((previous) => {
            if (!previous[groupId]) {
              return previous;
            }

            const next = { ...previous };
            delete next[groupId];
            return next;
          });

          if (editingGroupId === groupId) {
            closeGroupNameModal();
          }
        },
      });
    };

    const handleDeleteEntireGroup = (groupId: string) => {
      Modal.confirm({
        title: t('dashboard.deleteEntireGroup'),
        content: t('dashboard.deleteEntireGroupConfirm'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: async () => {
          removeLayoutItems(
            new Set([groupId, ...getDashboardGroupWidgetIds(layout, groupId)]),
          );
          setCollapsedGroups((previous) => {
            if (!previous[groupId]) {
              return previous;
            }

            const next = { ...previous };
            delete next[groupId];
            return next;
          });

          if (editingGroupId === groupId) {
            closeGroupNameModal();
          }
        },
      });
    };

    const handleEdit = (id: string) => {
      const item = layout.find((i) => i.i === id);
      if (!item || !isDashboardWidgetItem(item)) {
        return;
      }

      setCurrentConfigItem(item);
      setIsNewComponentConfig(false);
      setConfigDrawerVisible(true);
    };

    const handleOpenConfig = (item: ComponentSelectorConfigItem) => {
      setAddModalVisible(false);

      const configItem = {
        i: '',
        x: 0,
        y: 0,
        w: item.defaultWidth,
        h: item.defaultHeight,
        name: item.name,
        description: item.desc,
        valueConfig: {
          dataSource: item.dataSource,
          chartType: item.chartType,
          sceneWidgetType: item.sceneWidgetType,
          dataSourceParams: [],
        },
      };
      setCurrentConfigItem(configItem);
      setIsNewComponentConfig(true);
      setConfigDrawerVisible(true);
    };

    const handleConfigConfirm = (values: WidgetConfig) => {
      if (isNewComponentConfig && currentConfigItem) {
        handleAddComponent(values, currentConfigItem);
      } else {
        const editedWidgetId = currentConfigItem?.i;
        const nextLayout = layout.map((item) => {
          if (item.i === editedWidgetId && isDashboardWidgetItem(item)) {
            const nextChartType =
              values.chartType || item.valueConfig?.chartType || '';
            return {
              ...item,
              name: values.name,
              description: values.description,
              valueConfig: mergeSanitizedWidgetValueConfig(
                item.valueConfig,
                {
                  dataSource: values.dataSource,
                  chartType: values.chartType,
                  sceneWidgetType: values.sceneWidgetType,
                  networkStatusTopology: values.networkStatusTopology,
                  dataSourceParams: values.dataSourceParams,
                  tableConfig: values.tableConfig,
                  filterBindings: values.filterBindings,
                  selectedFields: values.selectedFields,
                  descriptionField: values.descriptionField,
                  topNLabelField: values.topNLabelField,
                  topNValueField: values.topNValueField,
                  unit: values.unit,
                  unitId: values.unitId,
                  valueMappings: values.valueMappings,
                  chartThemeMode: values.chartThemeMode,
                  appearance: values.appearance,
                  conversionFactor: values.conversionFactor,
                  decimalPlaces: values.decimalPlaces,
                  thresholdColors: values.thresholdColors,
                  gaugeMin: values.gaugeMin,
                  gaugeMax: values.gaugeMax,
                  gaugeShape: values.gaugeShape,
                  cardList: values.cardList,
                  compare: values.compare,
                  compareMode: values.compareMode,
                  actions: values.actions,
                },
                nextChartType,
              ),
            };
          }
          return item;
        });

        const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
        const syncedLayout = syncLayoutFilterBindings(
          nextLayout,
          nextDefinitions,
        );
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
      setPendingNewWidgetGroupId(null);
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
      const snapshot = buildFilterConfigConfirmSnapshot(
        newDefinitions,
        filterValues,
        appliedFilterValues,
      );
      updateDefinitions(snapshot.definitions);
      setAppliedFilterDefinitions(snapshot.definitions);
      setFilterValues(snapshot.filterValues);
      setAppliedFilterValues(snapshot.appliedFilterValues);
    };

    const handleCopy = (id: string) => {
      if (!isEditMode || shareMode) return;
      const nextLayout = copyDashboardWidget(layout, id);
      if (nextLayout === layout) return;

      const nextDefinitions = buildFiltersFromLayout(nextLayout, definitions);
      const syncedLayout = syncLayoutFilterBindings(
        nextLayout,
        nextDefinitions,
      );
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

    const handleShare = () => {
      void openShare(selectedDashboard?.data_id);
    };

    const dashboardToolbar = renderMode ? null : (
      <DashboardToolbar
        selectedDashboard={selectedDashboard}
        chartTheme={chartTheme}
        exporting={exporting}
        isFullscreen={isFullscreen}
        isEditMode={isEditMode}
        saving={saving}
        onRefresh={handleRefresh}
        frequenceValue={effectiveRefreshInterval}
        onFrequencyChange={handleFrequencyChange}
        onToggleFullscreen={handleFullscreenToggle}
        onExportPdf={handleExportPdf}
        onOpenFilterConfig={() => setFilterConfigModalVisible(true)}
        onOpenAddView={() => openAddModal()}
        onOpenAddGroup={handleAddGroup}
        onToggleEditMode={toggleEditMode}
        onCancelEdit={handleCancelEdit}
        onSave={handleSave}
        editExtra={bindCanvasDraftControls(dashboardDraft)}
        shareMode={shareMode}
        shareLoading={shareLoading}
        onOpenShare={!shareMode && selectedDashboard?.data_id ? handleShare : undefined}
        onOpenSubscriptions={
          !shareMode && selectedDashboard?.data_id
            ? () => setSubscriptionModalVisible(true)
            : undefined
        }
      />
    );

    const dashboardFilterBar = (definitions.length > 0 ||
      namespaceSelectorElement) && (
      <UnifiedFilterBar
        definitions={definitions}
        values={filterValues}
        onSearch={handleFilterSearch}
        onReset={handleFilterReset}
        prefixContent={namespaceSelectorElement}
        popupZIndex={isFullscreen ? 1200 : undefined}
      />
    );

    const dashboardCanvas = (
      <div
        ref={canvasScrollRef}
        className={
          renderMode ? 'w-full overflow-visible' : 'h-full overflow-auto'
        }
        data-export-expand="true"
      >
        <DashboardCanvas
          dashboardId={selectedDashboard?.data_id}
          loading={loading}
          isEditMode={isEditMode}
          isDarkTheme={isDarkTheme}
          key={selectedDashboard?.data_id ?? 'dashboard'}
          layout={layout}
          collapsedGroups={collapsedGroups}
          chartTheme={chartTheme}
          filterSearchVersion={filterSearchVersion}
          namespaceSearchVersion={namespaceSearchVersion}
          dashboardReloadVersion={dashboardReloadVersion}
          refreshCause={refreshCause}
          widgetReloadVersions={widgetReloadVersions}
          dataSourceResolver={dataSourceManager.findDataSource}
          appliedFilterValues={appliedFilterValues}
          appliedFilterDefinitions={appliedFilterDefinitions}
          appliedNamespaceId={appliedNamespaceId}
          selectedDashboardLocked={selectedDashboard?.is_build_in}
          shareMode={shareMode}
          onOpenAddModal={openAddModal}
          onLayoutChange={handleLayoutCommit}
          onToggleCollapsedGroup={toggleCollapsedGroup}
          onRenameGroup={handleRenameGroup}
          onRemoveGroup={handleRemoveGroup}
          onDeleteEntireGroup={handleDeleteEntireGroup}
          onEditWidget={handleEdit}
          onCopyWidget={handleCopy}
          onDeleteWidget={handleDelete}
          onTopologyLayoutChange={
            isEditMode && !shareMode ? handleTopologyLayoutChange : undefined
          }
          renderMode={renderMode}
          scrollRootRef={canvasScrollRef}
          onWidgetRenderStatus={handleWidgetRenderStatus}
        />
      </div>
    );

    return (
      <div
        className={`flex flex-col ${
          isFullscreen
            ? 'fixed inset-0 h-screen w-screen overflow-hidden'
            : renderMode
              ? 'w-full min-h-screen overflow-visible'
              : 'h-full flex-1 overflow-auto'
        }`}
        style={{
          backgroundColor: isDarkTheme ? 'var(--color-bg-2)' : '#f7f8fa',
          zIndex: isFullscreen ? 1100 : undefined,
        }}
      >
        <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
        {renderMode ? (
          <div
            className="z-[9999] w-full min-h-screen overflow-visible bg-[#f7f8fa] p-4"
            data-dashboard-render-root="true"
          >
            {dashboardCanvas}
          </div>
        ) : (
          <ViewWorkspace
            selectedItem={selectedDashboard}
            loading={loading}
            titleFallback="仪表盘"
            emptyDescription={t('dashboard.selectDashboardFirst')}
            headerVisible={!isFullscreen}
            filterBarVisible
            toolbar={dashboardToolbar}
            filterBar={dashboardFilterBar}
            contentRef={exportRef}
            contentClassName={
              isDarkTheme ? 'bg-[var(--color-bg-2)]' : 'bg-[#f7f8fa]'
            }
          >
            {dashboardCanvas}
          </ViewWorkspace>
        )}

        <ViewSelector
          visible={addModalVisible}
          onCancel={closeAddModal}
          onOpenConfig={handleOpenConfig}
        />
        <ViewConfig
          open={configDrawerVisible}
          item={currentConfigItem}
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
          layoutItems={widgetLayoutItems}
          dataSources={dataSourceManager.dataSources}
        />
        {selectedDashboard?.data_id && (
          <DashboardSubscriptionModal
            open={subscriptionModalVisible}
            dashboardId={Number(selectedDashboard.data_id)}
            appliedFilterValues={appliedFilterValues}
            onClose={() => setSubscriptionModalVisible(false)}
          />
        )}
        <Modal
          title={
            isCreatingGroupName
              ? t('dashboard.addGroup')
              : t('dashboard.editGroup')
          }
          open={groupNameModalVisible}
          onOk={handleGroupNameConfirm}
          onCancel={closeGroupNameModal}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          okButtonProps={{ disabled: !groupNameDraft.trim() }}
          centered
        >
          <Input
            value={groupNameDraft}
            onChange={(event) => setGroupNameDraft(event.target.value)}
            placeholder={t('dashboard.groupNamePlaceholder')}
            maxLength={50}
          />
        </Modal>
      </div>
    );
  },
);

Dashboard.displayName = 'Dashboard';

export default Dashboard;
