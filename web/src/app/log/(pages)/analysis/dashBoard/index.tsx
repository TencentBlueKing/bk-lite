'use client';

import React, {
  useState,
  useEffect,
  forwardRef,
  useRef,
  useImperativeHandle,
} from 'react';
import TimeSelector from '@/components/time-selector';
// @ts-expect-error missing type declarations for react-grid-layout
import GridLayout, { WidthProvider } from 'react-grid-layout';
import { Button, Dropdown, Menu, Modal, Spin, Select } from 'antd';
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
  editable?: boolean;
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const ResponsiveGridLayout = WidthProvider(GridLayout);

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  ({ selectedDashboard, editable = false }, ref) => {
    const { t } = useTranslation();
    const { getLogStreams } = useIntegrationApi();
    const { isLoading } = useApiClient();
    const timeSelectorRef = useRef<TimeSelectorRef>(null);
    const [layout, setLayout] = useState<LayoutItem[]>([]);
    const [originalLayout, setOriginalLayout] = useState<LayoutItem[]>([]);
    const [refreshKey, setRefreshKey] = useState(0);
    const [otherConfig, setOtherConfig] = useState<any>({});
    const [originalOtherConfig, setOriginalOtherConfig] = useState<any>({});
    const [pageLoading, setPageLoading] = useState<boolean>(false);
    const timeDefaultValue: TimeSelectorDefaultValue = {
      selectValue: 15,
      rangePickerVaule: null,
    };
    const [groups, setGroups] = useState<React.Key[]>([]);
    const [groupList, setGroupList] = useState<ListItem[]>([]);

    // 监听 selectedDashboard 的变化，重置状态
    useEffect(() => {
      setRefreshKey(0);
      if (!isLoading) {
        initData();
      }
      if (!selectedDashboard) {
        setLayout([]);
        setOriginalLayout([]);
        setOtherConfig({});
        setOriginalOtherConfig({});
        return;
      }
      const viewSets = selectedDashboard.view_sets || [];
      setLayout(viewSets);
      setOriginalLayout([...viewSets]);
      const savedOtherConfig = selectedDashboard.other || {};
      setOtherConfig(savedOtherConfig);
      setOriginalOtherConfig({ ...savedOtherConfig });
    }, [selectedDashboard?.id, isLoading]);

    const onFrequenceChange = (val: number) => {
      setOtherConfig((prev: any) => ({
        ...prev,
        frequence: val,
      }));
    };

    // 暴露方法给父组件
    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    const getTimeRange = () => {
      return timeSelectorRef.current?.getValue() || [];
    };

    const initData = async () => {
      try {
        setPageLoading(true);
        const data = await getLogStreams({
          page_size: -1,
          page: 1,
        });
        const list = data || [];
        const ids = list.at()?.id ? [list.at().id] : [];
        setGroupList(list);
        setGroups(ids);
        setOtherConfig((prev: any) => ({
          ...prev,
          groupIds: ids,
        }));
      } finally {
        setPageLoading(false);
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
      // 更新全局时间范围
      setOtherConfig((prev: any) => ({
        ...prev,
        timeRange: range,
      }));
    };

    const onGroupChange = (val: React.Key[]) => {
      setGroups(val);
      setOtherConfig((prev: any) => ({
        ...prev,
        groupIds: val,
      }));
    };

    const handleRefresh = () => {
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
        view_sets: layout,
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
        },
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
            `,
            }}
          />
        )}
        <div className="w-full mb-2 flex items-center justify-between rounded-lg shadow-sm bg-[var(--color-bg-1)] p-3 border border-[var(--color-border-2)]">
          {selectedDashboard && (
            <div className="p-1 pt-0">
              <h2 className="text-lg font-semibold mb-1 text-[var(--color-text-1)]">
                {t('log.analysis.dashboard')}
              </h2>
              <p className="text-sm text-[var(--color-text-2)]">
                {selectedDashboard.desc}
              </p>
            </div>
          )}
          <div className="flex items-center space-x-4 justify-between">
            <Select
              style={{
                width: '250px',
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
            {
              <div className="flex items-center space-x-2 py-2">
                <TimeSelector
                  ref={timeSelectorRef}
                  key={`time-selector-${selectedDashboard?.id || 'default'}`}
                  defaultValue={timeDefaultValue}
                  onChange={handleTimeChange}
                  onRefresh={handleRefresh}
                  onFrequenceChange={onFrequenceChange}
                />
              </div>
            }
            {editable && (
              <Button
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
