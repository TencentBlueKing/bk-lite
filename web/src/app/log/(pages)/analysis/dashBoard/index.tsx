'use client';

import React, {
  useState,
  useEffect,
  forwardRef,
  useRef,
  useImperativeHandle
} from 'react';
import TimeSelector from '@/components/time-selector';
import GridLayout, { WidthProvider } from 'react-grid-layout';
import { Button, Modal, Spin, Select, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { LayoutItem, DirItem } from '@/app/log/types/analysis';
import { SearchOutlined, SaveOutlined } from '@ant-design/icons';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import WidgetWrapper from './components/widgetWrapper';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { ListItem } from '@/app/log/types';
import { TimeSelectorDefaultValue, TimeSelectorRef } from '@/types';
import useIntegrationApi from '@/app/log/api/integration';
import useApiClient from '@/utils/request';

const { Option } = Select;
const ResponsiveGridLayout = WidthProvider(GridLayout);

interface DashboardProps {
  selectedDashboard?: DirItem | null;
  selectedDashboardTitle?: string;
  selectedCollectTypeId?: React.Key | null;
  editable?: boolean;
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  (
    {
      selectedDashboard,
      selectedDashboardTitle = '',
      selectedCollectTypeId = null,
      editable = false
    },
    ref
  ) => {
    const { t } = useTranslation();
    const { getLogStreams, getInstanceList, getFieldValues } =
      useIntegrationApi();
    const { isLoading } = useApiClient();
    const timeSelectorRef = useRef<TimeSelectorRef>(null);
    const instanceAbortControllerRef = useRef<AbortController | null>(null);
    const instanceRequestIdRef = useRef(0);
    const [layout, setLayout] = useState<LayoutItem[]>([]);
    const [originalLayout, setOriginalLayout] = useState<LayoutItem[]>([]);
    const [refreshKey, setRefreshKey] = useState(0);
    const [otherConfig, setOtherConfig] = useState<any>({});
    const [originalOtherConfig] = useState<any>({});
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const timeDefaultValue: TimeSelectorDefaultValue = {
      selectValue: 15,
      rangePickerVaule: null
    };
    const [groups, setGroups] = useState<React.Key[]>([]);
    const [groupList, setGroupList] = useState<ListItem[]>([]);
    const [instanceOptions, setInstanceOptions] = useState<ListItem[]>([]);
    const [instanceIds, setInstanceIds] = useState<React.Key[]>([]);
    const [instanceLoading, setInstanceLoading] = useState(false);
    const [containerOptions, setContainerOptions] = useState<ListItem[]>([]);
    const [containerNames, setContainerNames] = useState<React.Key[]>([]);
    const [containerLoading, setContainerLoading] = useState(false);
    const collectTypeName = selectedDashboard?.collectTypeName || '';
    const showInstanceFilter = !!collectTypeName;
    const showContainerFilter = collectTypeName === 'docker';

    // 初始化分组数据（仅首次加载）
    useEffect(() => {
      if (!isLoading) {
        initData();
      }
    }, [isLoading]);

    // 监听 selectedDashboard 的变化，仅更新 layout，保留筛选条件
    useEffect(() => {
      if (!selectedDashboard) {
        setLayout([]);
        setOriginalLayout([]);
        setInstanceIds([]);
        setInstanceOptions([]);
        return;
      }
      const viewSets = selectedDashboard.view_sets || [];
      setLayout(viewSets);
      setOriginalLayout([...viewSets]);
      setRefreshKey((prev) => prev + 1);
    }, [selectedDashboard?.id]);

    useEffect(() => {
      if (!showInstanceFilter) {
        instanceAbortControllerRef.current?.abort();
        setInstanceIds([]);
        setInstanceOptions([]);
        setOtherConfig((prev: any) => ({
          ...prev,
          instanceIds: []
        }));
        return;
      }

      setInstanceIds([]);
      setOtherConfig((prev: any) => ({
        ...prev,
        instanceIds: []
      }));

      if (!isLoading) {
        loadInstancesByCollectType(selectedCollectTypeId);
      }
    }, [collectTypeName, isLoading, selectedCollectTypeId, showInstanceFilter]);

    useEffect(() => {
      if (!showContainerFilter || !groups.length) {
        setContainerNames([]);
        setContainerOptions([]);
        setOtherConfig((prev: any) => ({
          ...prev,
          containerNames: []
        }));
        return;
      }

      loadDockerContainers();
    }, [showContainerFilter, groups, otherConfig.timeRange]);

    useEffect(() => {
      return () => {
        instanceAbortControllerRef.current?.abort();
      };
    }, []);

    const onFrequenceChange = (val: number) => {
      setOtherConfig((prev: any) => ({
        ...prev,
        frequence: val
      }));
    };

    const buildInstanceFilterQuery = (
      queryText: string,
      selectedInstanceIds?: Array<string | number>
    ) => {
      if (!selectedInstanceIds?.length) {
        return queryText;
      }

      const instanceFilter =
        selectedInstanceIds.length === 1
          ? `instance_id:"${String(selectedInstanceIds[0])}"`
          : `(${selectedInstanceIds.map((id) => `instance_id:"${String(id)}"`).join(' OR ')})`;

      const separatorIndex = queryText.indexOf('|');
      const baseFilter =
        separatorIndex >= 0
          ? queryText.slice(0, separatorIndex).trim()
          : queryText.trim();
      const pipeline =
        separatorIndex >= 0 ? queryText.slice(separatorIndex).trimStart() : '';

      const mergedFilter =
        !baseFilter || baseFilter === '*'
          ? instanceFilter
          : `(${baseFilter}) AND ${instanceFilter}`;

      return pipeline ? `${mergedFilter} ${pipeline}` : mergedFilter;
    };

    const buildContainerFilterQuery = (
      queryText: string,
      selectedContainerNames?: Array<string | number>
    ) => {
      if (!selectedContainerNames?.length) {
        return queryText;
      }

      const containerFilter =
        selectedContainerNames.length === 1
          ? `container_name:"${String(selectedContainerNames[0])}"`
          : `(${selectedContainerNames.map((name) => `container_name:"${String(name)}"`).join(' OR ')})`;

      const separatorIndex = queryText.indexOf('|');
      const baseFilter =
        separatorIndex >= 0
          ? queryText.slice(0, separatorIndex).trim()
          : queryText.trim();
      const pipeline =
        separatorIndex >= 0 ? queryText.slice(separatorIndex).trimStart() : '';

      const mergedFilter =
        !baseFilter || baseFilter === '*'
          ? containerFilter
          : `(${baseFilter}) AND ${containerFilter}`;

      return pipeline ? `${mergedFilter} ${pipeline}` : mergedFilter;
    };

    const calculateTimeInterval = (
      startTime: string,
      endTime: string
    ): string => {
      const start = new Date(startTime);
      const end = new Date(endTime);
      const diffInHours =
        Math.abs(end.getTime() - start.getTime()) / (1000 * 60 * 60);

      if (diffInHours <= 24) {
        return '1m';
      } else if (diffInHours <= 720) {
        return '1h';
      }
      return '1d';
    };

    const buildWidgetSearchQuery = (item: LayoutItem) => {
      const times = getTimeRange();
      const startTime = times?.[0] ? new Date(times[0]).toISOString() : '';
      const endTime = times?.[1] ? new Date(times[1]).toISOString() : '';
      const dataSourceParams = item.valueConfig?.dataSourceParams as
        | { query?: string; searchQuery?: string }
        | undefined;
      let query =
        dataSourceParams?.searchQuery || dataSourceParams?.query || '*';

      if (query.includes('${_time}') && startTime && endTime) {
        query = query.replace(
          /\$\{_time\}/g,
          calculateTimeInterval(startTime, endTime)
        );
      }

      query = buildInstanceFilterQuery(query, otherConfig.instanceIds);
      query = buildContainerFilterQuery(query, otherConfig.containerNames);

      return query;
    };

    const handleOpenSearch = (item: LayoutItem) => {
      const times = getTimeRange();
      const params = new URLSearchParams();
      const query = buildWidgetSearchQuery(item);

      params.set('query', query);
      if (times?.[0]) {
        params.set('startTime', String(times[0]));
      }
      if (times?.[1]) {
        params.set('endTime', String(times[1]));
      }
      groups.forEach((groupId) => {
        params.append('log_groups', String(groupId));
      });

      window.open(
        `/log/search?${params.toString()}`,
        '_blank',
        'noopener,noreferrer'
      );
    };

    // 暴露方法给父组件
    useImperativeHandle(ref, () => ({
      hasUnsavedChanges
    }));

    const getTimeRange = () => {
      const value = timeSelectorRef.current?.getValue?.() as any;
      return value || [];
    };

    const initData = async () => {
      try {
        setPageLoading(true);
        const data = await getLogStreams({
          page_size: -1,
          page: 1
        });
        const list = data || [];
        const ids = list.at()?.id ? [list.at().id] : [];
        setGroupList(list);
        setGroups(ids);
        if (!ids.length) {
          message.error(t('log.search.searchError'));
        }
        setOtherConfig((prev: any) => ({
          ...prev,
          groupIds: ids
        }));
      } finally {
        setPageLoading(false);
      }
    };

    const loadInstancesByCollectType = async (
      collectTypeId: React.Key | null
    ) => {
      instanceAbortControllerRef.current?.abort();
      const abortController = new AbortController();
      instanceAbortControllerRef.current = abortController;
      const currentRequestId = ++instanceRequestIdRef.current;

      try {
        setInstanceLoading(true);
        if (!collectTypeId) {
          setInstanceOptions([]);
          return;
        }
        const instanceData = await getInstanceList(
          {
            collect_type_id: collectTypeId,
            page: 1,
            page_size: -1
          },
          { signal: abortController.signal }
        );
        if (currentRequestId !== instanceRequestIdRef.current) return;

        setInstanceOptions(
          ((instanceData?.items as ListItem[]) || []).map((item) => ({
            id: item.id,
            name: item.name
          }))
        );
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED')
          return;
        setInstanceOptions([]);
      } finally {
        if (currentRequestId === instanceRequestIdRef.current) {
          setInstanceLoading(false);
        }
      }
    };

    // 检查是否有未保存的更改
    const hasUnsavedChanges = () => {
      if (
        originalLayout.length === 0 &&
        layout.length === 0 &&
        Object.keys(originalOtherConfig).length === 0 &&
        Object.keys(otherConfig).length === 0
      ) {
        return false;
      }
      try {
        const layoutChanged =
          JSON.stringify(layout) !== JSON.stringify(originalLayout);
        const otherConfigChanged =
          JSON.stringify(otherConfig) !== JSON.stringify(originalOtherConfig);
        return layoutChanged || otherConfigChanged;
      } catch (error) {
        console.error('检查未保存更改时出错:', error);
        return false;
      }
    };

    const handleTimeChange = (range: number[]) => {
      if (!groups.length) {
        message.error(t('log.search.searchError'));
        return;
      }
      // 更新全局时间范围
      setOtherConfig((prev: any) => ({
        ...prev,
        timeRange: range
      }));
    };

    const onGroupChange = (val: React.Key[]) => {
      setGroups(val);
      if (!val.length) {
        message.error(t('log.search.searchError'));
      }
      setOtherConfig((prev: any) => ({
        ...prev,
        groupIds: val
      }));
    };

    const onInstanceChange = (val: React.Key[]) => {
      setInstanceIds(val);
      setOtherConfig((prev: any) => ({
        ...prev,
        instanceIds: val
      }));
    };

    const onContainerChange = (val: React.Key[]) => {
      setContainerNames(val);
      setOtherConfig((prev: any) => ({
        ...prev,
        containerNames: val
      }));
    };

    const loadDockerContainers = async () => {
      try {
        setContainerLoading(true);
        const times = getTimeRange();
        const values = await getFieldValues({
          filed: 'container_name',
          start_time: times?.[0] ? new Date(times[0]).toISOString() : '',
          end_time: times?.[1] ? new Date(times[1]).toISOString() : '',
          limit: 100,
          log_groups: groups
        });

        const options = (
          (values?.values as Array<
            string | { value?: string; hits?: number }
          >) || []
        )
          .map((item) => {
            if (typeof item === 'string') {
              return item;
            }
            return item?.value || '';
          })
          .filter(Boolean)
          .map((value) => ({ id: value, name: value }));

        setContainerOptions(options);
      } catch {
        setContainerOptions([]);
      } finally {
        setContainerLoading(false);
      }
    };

    const handleRefresh = () => {
      if (!groups.length) {
        message.error(t('log.search.searchError'));
        return;
      }
      // 重新获取时间选择器的最新值，确保定时刷新时时间范围是最新的
      const latestTimeRange = getTimeRange();
      setOtherConfig((prev: any) => ({
        ...prev,
        timeRange: latestTimeRange
      }));
      setRefreshKey((prev) => prev + 1);
    };

    const onLayoutChange = (newLayout: any) => {
      setLayout((prevLayout) => {
        return prevLayout.map((item) => {
          const newItem = newLayout.find((l: any) => l.i === item.i);
          if (newItem) {
            return { ...item, ...newItem };
          }
          return item;
        });
      });
    };

    const handleSave = () => {
      const saveData = {
        name: selectedDashboard?.name,
        desc: selectedDashboard?.desc || '',
        filters: {},
        other: otherConfig,
        view_sets: layout
      };
      console.log(saveData);
    };

    const removeWidget = (id: string) => {
      setLayout(layout.filter((item) => item.i !== id));
    };

    const handleDelete = (id: string) => {
      Modal.confirm({
        title: t('common.delConfirm'),
        content: t('common.delConfirmCxt'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        centered: true,
        onOk: async () => {
          try {
            removeWidget(id);
          } catch {
            console.error(t('common.operateFailed'));
          }
        }
      });
    };

    return (
      <div className="h-full flex-1 overflow-auto bg-[var(--color-bg-1)]">
        {!editable && (
          <style
            dangerouslySetInnerHTML={{
              __html: `
              .readonly-widget .react-resizable-handle {
                display: none !important;
              }
            `
            }}
          />
        )}
        <div className="flex min-h-full flex-col gap-4 p-4">
          <div className="w-full overflow-x-auto rounded-2xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)]/95 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
              {selectedDashboard && (
                <h2 className="whitespace-nowrap text-xl font-semibold text-[var(--color-text-1)]">
                  {getDashboardTitle(
                    selectedDashboardTitle || selectedDashboard.name
                  )}
                </h2>
              )}
              <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
                <div className="flex flex-none items-center">
                  <TimeSelector
                    className="flex-none"
                    ref={timeSelectorRef}
                    key="time-selector"
                    defaultValue={timeDefaultValue}
                    onChange={handleTimeChange}
                    onRefresh={handleRefresh}
                    onFrequenceChange={onFrequenceChange}
                  />
                </div>
                {editable && (
                  <Button
                    className="flex-none"
                    icon={<SaveOutlined />}
                    disabled={!selectedDashboard?.id}
                    onClick={handleSave}
                  >
                    {t('common.save')}
                  </Button>
                )}
              </div>
            </div>

            <div className="mt-4 flex min-w-0 flex-wrap gap-2">
              <div className="w-[200px] max-w-full">
                <div className="mb-1 text-xs font-medium text-[var(--color-text-3)]">
                  {t('log.integration.logGroup')}
                </div>
                <Select
                  className="w-full"
                  loading={pageLoading}
                  showSearch
                  mode="multiple"
                  maxTagCount="responsive"
                  placeholder={t('log.search.selectGroup')}
                  value={groups}
                  onChange={(val) => onGroupChange(val)}
                >
                  {groupList.map((item) => (
                    <Option value={item.id} key={item.id}>
                      {item.name}
                    </Option>
                  ))}
                </Select>
              </div>

              {showInstanceFilter && (
                <div className="w-[200px] max-w-full">
                  <div className="mb-1 text-xs font-medium text-[var(--color-text-3)]">
                    {t('log.instance')}
                  </div>
                  <Select
                    className="w-full"
                    loading={instanceLoading}
                    showSearch
                    mode="multiple"
                    maxTagCount="responsive"
                    placeholder={t('log.analysis.selectInstance')}
                    value={instanceIds}
                    onChange={(val) => onInstanceChange(val)}
                    optionFilterProp="children"
                  >
                    {instanceOptions.map((item) => (
                      <Option value={item.id} key={item.id}>
                        {item.name}
                      </Option>
                    ))}
                  </Select>
                </div>
              )}

              {showContainerFilter && (
                <div className="w-[200px] max-w-full">
                  <div className="mb-1 text-xs font-medium text-[var(--color-text-3)]">
                    {t('log.analysis.container')}
                  </div>
                  <Select
                    className="w-full"
                    loading={containerLoading}
                    showSearch
                    mode="multiple"
                    maxTagCount="responsive"
                    placeholder={t('log.analysis.selectContainer')}
                    value={containerNames}
                    onChange={(val) => onContainerChange(val)}
                    optionFilterProp="children"
                  >
                    {containerOptions.map((item) => (
                      <Option value={item.id} key={item.id}>
                        {item.name}
                      </Option>
                    ))}
                  </Select>
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {(() => {
              if (pageLoading) {
                return (
                  <div className="h-full flex flex-col items-center justify-center">
                    <Spin spinning={pageLoading} />
                  </div>
                );
              }
              return (
                <ResponsiveGridLayout
                  className="layout w-full flex-1"
                  layout={layout as LayoutItem[]}
                  onLayoutChange={editable ? onLayoutChange : undefined}
                  cols={12}
                  rowHeight={88}
                  margin={[14, 14]}
                  containerPadding={[8, 8]}
                  draggableCancel=".no-drag, .widget-body"
                  isDraggable={editable}
                  isResizable={editable}
                >
                  {(layout as LayoutItem[]).map((item) => {
                    return (
                      <div
                        key={item.i}
                        className={`widget flex flex-col overflow-hidden rounded-[18px] border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-4 pb-4 pt-3 shadow-[0_4px_20px_rgba(15,23,42,0.08)] ${
                          !editable ? 'readonly-widget' : ''
                        }`}
                      >
                        <div className="widget-header pb-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1">
                                <h4 className="truncate text-[15px] font-semibold text-[var(--color-text-1)]">
                                  {item.name}
                                </h4>
                              </div>
                            </div>
                            <div className="no-drag flex items-center gap-1">
                              <Button
                                type="link"
                                className="m-0 p-0"
                                icon={<SearchOutlined />}
                                onClick={() => handleOpenSearch(item)}
                                title={t('log.integration.viewLogs')}
                              />
                              {editable && (
                                <MoreActionsDropdown
                                  items={[
                                    {
                                      key: 'delete',
                                      label: t('common.delete'),
                                      onClick: () => handleDelete(item.i),
                                    },
                                  ]}
                                  buttonClassName="no-drag text-[var(--color-text-2)] hover:text-[var(--color-text-1)] transition-colors"
                                  iconStyle={{ fontSize: '20px' }}
                                />
                              )}
                            </div>
                          </div>
                          {item.description && (
                            <EllipsisWithTooltip
                              text={item.description}
                              className="truncate text-xs text-[var(--color-text-3)] cursor-default"
                            />
                          )}
                        </div>
                        <div className="widget-body h-full flex-1 overflow-hidden bg-[var(--color-bg-1)]">
                          <WidgetWrapper
                            key={item.i}
                            chartType={item.valueConfig?.chartType}
                            config={{
                              ...item.valueConfig,
                              description: item.description
                            }}
                            otherConfig={otherConfig}
                            globalTimeRange={getTimeRange()}
                            refreshKey={refreshKey}
                            editable={editable}
                            getLatestTimeRange={getTimeRange}
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
    );
  }
);

const getDashboardTitle = (label: string) => {
  if (!label) {
    return '';
  }

  return label.endsWith('仪表盘') ? label : `${label}仪表盘`;
};

Dashboard.displayName = 'Dashboard';

export default Dashboard;
