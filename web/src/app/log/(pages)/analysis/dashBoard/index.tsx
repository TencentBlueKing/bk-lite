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
import { Button, Dropdown, Menu, Modal, Spin, Select, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { LayoutItem, DirItem } from '@/app/log/types/analysis';
import { SaveOutlined, MoreOutlined } from '@ant-design/icons';
import WidgetWrapper from './components/widgetWrapper';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { ListItem } from '@/app/log/types';
import { TimeSelectorDefaultValue, TimeSelectorRef } from '@/types';
import useIntegrationApi from '@/app/log/api/integration';
import useApiClient from '@/utils/request';

const { Option } = Select;

interface DashboardProps {
  selectedDashboard?: DirItem | null;
  selectedCollectTypeId?: React.Key | null;
  editable?: boolean;
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const ResponsiveGridLayout = WidthProvider(GridLayout);

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  (
    { selectedDashboard, selectedCollectTypeId = null, editable = false },
    ref
  ) => {
    const { t } = useTranslation();
    const { getLogStreams, getInstanceList } = useIntegrationApi();
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
    const collectTypeName = selectedDashboard?.collectTypeName || '';
    const showInstanceFilter = !!collectTypeName;

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
      if (!groups.length && !isLoading) {
        message.error(t('log.search.searchError'));
        return;
      }
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
            page_size: 1000
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
      <div className="h-full flex-1 p-4 pb-0 overflow-auto flex flex-col bg-[var(--color-bg-1)]">
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
        <div className="w-full mb-2 flex items-center justify-between gap-3 overflow-x-auto rounded-lg shadow-sm bg-[var(--color-bg-1)] p-3 border border-[var(--color-border-2)]">
          {selectedDashboard && (
            <div className="min-w-fit shrink-0 p-1 pt-0">
              <h2 className="mb-1 whitespace-nowrap text-lg font-semibold text-[var(--color-text-1)]">
                {t('log.analysis.dashboard')}
              </h2>
              <p className="max-w-[220px] truncate text-sm text-[var(--color-text-2)]">
                {selectedDashboard.desc}
              </p>
            </div>
          )}
          <div className="mx-4 my-2 flex min-w-0 flex-1 items-center justify-end gap-2 whitespace-nowrap">
            <Select
              style={{
                width: '150px'
              }}
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
            {showInstanceFilter && (
              <Select
                className="w-[150px] flex-none"
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
            )}
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

        <div className="flex-1 bg-[var(--color-fill-1)] rounded-lg overflow-auto">
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
                layout={layout}
                onLayoutChange={editable ? onLayoutChange : undefined}
                cols={12}
                rowHeight={100}
                margin={[12, 12]}
                containerPadding={[12, 12]}
                draggableCancel=".no-drag, .widget-body"
                isDraggable={editable}
                isResizable={editable}
              >
                {layout.map((item) => {
                  const menu = (
                    <Menu>
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
                      className={`widget bg-[var(--color-bg-1)] rounded-lg shadow-sm overflow-hidden p-4 flex flex-col ${
                        !editable ? 'readonly-widget' : ''
                      }`}
                    >
                      <div className="widget-header pb-4 flex justify-between items-center">
                        <div className="flex-1">
                          <h4 className="text-md font-medium text-[var(--color-text-1)]">
                            {item.name}
                          </h4>
                          {
                            <p className="text-[12px] text-[var(--color-text-3)] mt-1">
                              {item.description || '--'}
                            </p>
                          }
                        </div>
                        {editable && (
                          <Dropdown overlay={menu} trigger={['click']}>
                            <button className="no-drag text-[var(--color-text-2)] hover:text-[var(--color-text-1)] transition-colors">
                              <MoreOutlined style={{ fontSize: '20px' }} />
                            </button>
                          </Dropdown>
                        )}
                      </div>
                      <div className="widget-body flex-1 h-full rounded-b overflow-hidden">
                        <WidgetWrapper
                          key={item.i}
                          chartType={item.valueConfig?.chartType}
                          config={item.valueConfig}
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
    );
  }
);

Dashboard.displayName = 'Dashboard';

export default Dashboard;
