'use client';

import React, {
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import dayjs from 'dayjs';
import { v4 as uuidv4 } from 'uuid';
import ViewSelector from './components/viewSelector';
import ViewConfig from './components/viewConfig';
import TimeSelector from '@/components/time-selector';
// @ts-expect-error missing type declarations for react-grid-layout
import GridLayout, { WidthProvider } from 'react-grid-layout';
import { Button, Empty, Dropdown, Menu, Modal, message, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import { DirItem } from '@/app/ops-analysis/types';
import { SaveOutlined, PlusOutlined, MoreOutlined } from '@ant-design/icons';
import { getWidgetMeta } from './config/registry';
import { useDashBoardApi } from '@/app/ops-analysis/api/dashBoard';
import WidgetWrapper from './components/widgetWrapper';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

interface DashboardProps {
  selectedDashboard?: DirItem | null;
}

export interface DashboardRef {
  hasUnsavedChanges: () => boolean;
}

const ResponsiveGridLayout = WidthProvider(GridLayout);

const Dashboard = forwardRef<DashboardRef, DashboardProps>(
  ({ selectedDashboard }, ref) => {
    const { t } = useTranslation();
    const { getDashboardDetail, saveDashboard } = useDashBoardApi();
    const [addModalVisible, setAddModalVisible] = useState(false);
    const [layout, setLayout] = useState<LayoutItem[]>([]);
    const [originalLayout, setOriginalLayout] = useState<LayoutItem[]>([]);
    const [configDrawerVisible, setConfigDrawerVisible] = useState(false);
    const [currentConfigItem, setCurrentConfigItem] = useState<any>(null);
    const [isNewComponentConfig, setIsNewComponentConfig] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(false);
    const [otherConfig, setOtherConfig] = useState<any>({});
    const [originalOtherConfig, setOriginalOtherConfig] = useState<any>({});
    const timeDefaultValue = {
      selectValue: 10080,
      rangePickerVaule: null,
    };

    const getInitialTimeRange = (savedTimeConfig?: any) => {
      const endTime = dayjs().valueOf();
      let timeValue = timeDefaultValue.selectValue;
      let rangePickerVaule = null;
      let selectValue = timeDefaultValue.selectValue;

      // 如果有保存的时间配置，优先使用保存的配置
      if (savedTimeConfig?.timeSelector) {
        selectValue =
          savedTimeConfig.timeSelector.selectValue ||
          timeDefaultValue.selectValue;
        rangePickerVaule = savedTimeConfig.timeSelector.rangePickerVaule;

        if (
          selectValue === 0 &&
          rangePickerVaule &&
          Array.isArray(rangePickerVaule)
        ) {
          // 使用自定义时间范围
          return {
            start: dayjs(rangePickerVaule[0]).valueOf(),
            end: dayjs(rangePickerVaule[1]).valueOf(),
            selectValue: 0,
            rangePickerVaule: rangePickerVaule,
          };
        } else {
          timeValue = selectValue;
        }
      }

      const startTime = dayjs().subtract(timeValue, 'minute').valueOf();
      return {
        start: startTime,
        end: endTime,
        selectValue: selectValue,
        rangePickerVaule: null,
      };
    };
    const [globalTimeRange, setGlobalTimeRange] = useState<any>(
      getInitialTimeRange()
    );

    // 判断是否需要全局时间选择器
    const needGlobalTimeSelector = layout.some((item) => {
      return (
        item.config?.dataSourceParams &&
        Array.isArray(item.config.dataSourceParams) &&
        item.config.dataSourceParams.some(
          (param: any) =>
            param.filterType === 'filter' && param.type === 'timeRange'
        )
      );
    });

    useEffect(() => {
      const loadDashboardData = async () => {
        if (!selectedDashboard) {
          setLayout([]);
          setOriginalLayout([]);
          setOtherConfig({});
          setOriginalOtherConfig({});
          return;
        }
        try {
          setLoading(true);
          const dashboardData = await getDashboardDetail(
            selectedDashboard.data_id
          );
          if (
            dashboardData.view_sets &&
            Array.isArray(dashboardData.view_sets)
          ) {
            setLayout(dashboardData.view_sets);
            setOriginalLayout([...dashboardData.view_sets]);
          } else {
            setLayout([]);
            setOriginalLayout([]);
          }

          const savedOtherConfig = dashboardData.other || {};
          setOtherConfig(savedOtherConfig);
          setOriginalOtherConfig({ ...savedOtherConfig });

          // 根据保存的配置初始化时间范围
          setGlobalTimeRange(getInitialTimeRange(savedOtherConfig));
        } catch (error) {
          console.error('加载仪表盘数据失败:', error);
          setLayout([]);
          setOriginalLayout([]);
          setOtherConfig({});
          setOriginalOtherConfig({});
        } finally {
          setLoading(false);
        }
      };
      loadDashboardData();
    }, [selectedDashboard?.data_id]);

    // 监听 selectedDashboard 的变化，重置状态
    useEffect(() => {
      setAddModalVisible(false);
      setConfigDrawerVisible(false);
      setCurrentConfigItem(null);
      setIsNewComponentConfig(false);
      setSaving(false);
      setRefreshKey(0);
    }, [selectedDashboard?.data_id]);

    const openAddModal = () => setAddModalVisible(true);

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

    // 暴露方法给父组件
    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    const handleTimeChange = (range: number[], originValue: number | null) => {
      // 更新全局时间范围
      const timeData = {
        start:
          range[0] ||
          dayjs().subtract(timeDefaultValue.selectValue, 'minute').valueOf(),
        end: range[1] || dayjs().valueOf(),
        selectValue: originValue,
        rangePickerVaule:
          originValue === 0 ? [dayjs(range[0]), dayjs(range[1])] : null,
      };

      setGlobalTimeRange(timeData);

      // 更新otherConfig中的timeSelector配置
      const timeSelectorConfig = {
        selectValue:
          originValue !== null ? originValue : timeDefaultValue.selectValue,
        rangePickerVaule:
          originValue === 0 ? [dayjs(range[0]), dayjs(range[1])] : null,
      };

      setOtherConfig((prev: any) => ({
        ...prev,
        timeSelector: timeSelectorConfig,
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

    const handleAddComponent = (widget: string, config?: any) => {
      const widgetMeta = getWidgetMeta(widget);
      const newWidget: LayoutItem = {
        i: uuidv4(),
        x: (layout.length % 3) * 4,
        y: Infinity,
        w: 4,
        h: 3,
        widget: widget,
        title: config?.name || `New ${widget}`,
        description: widgetMeta?.description || '',
        config: {
          ...widgetMeta?.defaultConfig,
          ...config,
        },
      };
      setLayout((prev) => [...prev, newWidget]);
      setAddModalVisible(false);
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
          filters: {},
          other: otherConfig,
          view_sets: layout,
        };
        await saveDashboard(selectedDashboard.data_id, saveData);
        setOriginalLayout([...layout]);
        setOriginalOtherConfig({ ...otherConfig });
        message.success(t('common.saveSuccess'));
      } catch (error) {
        console.error('保存仪表盘失败:', error);
      } finally {
        setSaving(false);
      }
    };

    const removeWidget = (id: string) => {
      setLayout(layout.filter((item) => item.i !== id));
    };

    const handleEdit = (id: string) => {
      const item = layout.find((i) => i.i === id);
      setCurrentConfigItem(item);
      setIsNewComponentConfig(false);
      setConfigDrawerVisible(true);
    };

    const handleOpenConfig = (item: any) => {
      setCurrentConfigItem(item);
      setIsNewComponentConfig(true);
      setConfigDrawerVisible(true);
    };

    const handleConfigConfirm = (values: any) => {
      if (isNewComponentConfig && currentConfigItem) {
        // 新组件：添加到布局中
        handleAddComponent(currentConfigItem.widget, values);
      } else {
        // 编辑现有组件：更新布局
        setLayout((prevLayout) =>
          prevLayout.map((item) => {
            if (item.i === currentConfigItem?.i) {
              return {
                ...item,
                title: values.name,
                config: {
                  ...item.config,
                  ...values,
                },
              };
            }
            return item;
          })
        );
      }
      setConfigDrawerVisible(false);
      setCurrentConfigItem(null);
      setIsNewComponentConfig(false);
    };

    const handleConfigClose = () => {
      setConfigDrawerVisible(false);
      setCurrentConfigItem(null);
      setIsNewComponentConfig(false);
    };

    const handleDelete = (id: string) => {
      Modal.confirm({
        title: t('deleteTitle'),
        content: t('deleteContent'),
        okText: t('confirm'),
        cancelText: t('cancel'),
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
        <div className="w-full mb-2 flex items-center justify-between rounded-lg shadow-sm bg-[var(--color-bg-1)] p-3 border border-[var(--color-border-2)]">
          {selectedDashboard && (
            <div className="p-1 pt-0">
              <h2 className="text-lg font-semibold mb-1 text-[var(--color-text-1)]">
                {selectedDashboard.name}
              </h2>
              <p className="text-sm text-[var(--color-text-2)]">
                {selectedDashboard.desc}
              </p>
            </div>
          )}
          <div className="flex items-center space-x-4 justify-between">
            {
              <div className="flex items-center space-x-2 py-2">
                <TimeSelector
                  key={`time-selector-${selectedDashboard?.data_id || 'default'}`}
                  onlyRefresh={!needGlobalTimeSelector}
                  defaultValue={otherConfig.timeSelector || timeDefaultValue}
                  onChange={handleTimeChange}
                  onRefresh={handleRefresh}
                />
              </div>
            }
            <Button
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!selectedDashboard?.data_id}
              onClick={handleSave}
            >
              {t('common.save')}
            </Button>
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              onClick={openAddModal}
              style={{ borderColor: '#1677ff', color: '#1677ff' }}
            >
              {t('dashboard.addComponent')}
            </Button>
          </div>
        </div>

        <div className="flex-1 bg-[var(--color-fill-1)] rounded-lg overflow-auto">
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
                      <span className="text-[var(--color-text-2)]">
                        {t('dashboard.addView')}
                      </span>
                    }
                  >
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={openAddModal}
                    >
                      {t('dashboard.addView')}
                    </Button>
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
                rowHeight={100}
                margin={[12, 12]}
                containerPadding={[12, 12]}
                draggableCancel=".no-drag, .widget-body"
              >
                {layout.map((item) => {
                  const menu = (
                    <Menu>
                      <Menu.Item key="edit" onClick={() => handleEdit(item.i)}>
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
                      className="widget bg-[var(--color-bg-1)] rounded-lg shadow-sm overflow-hidden p-4 flex flex-col"
                    >
                      <div className="widget-header pb-4 flex justify-between items-center">
                        <div className="flex-1">
                          <h4 className="text-md font-medium text-[var(--color-text-1)]">
                            {item.title}
                          </h4>
                          {
                            <p className="text-sm text-[var(--color-text-2)] mt-1">
                              {item.description || '--'}
                            </p>
                          }
                        </div>
                        <Dropdown overlay={menu} trigger={['click']}>
                          <button className="no-drag text-[var(--color-text-2)] hover:text-[var(--color-text-1)] transition-colors">
                            <MoreOutlined style={{ fontSize: '20px' }} />
                          </button>
                        </Dropdown>
                      </div>
                      <div className="widget-body flex-1 h-full rounded-b overflow-hidden">
                        <WidgetWrapper
                          key={item.i}
                          chartType={item.config?.chartType}
                          config={item.config}
                          globalTimeRange={globalTimeRange}
                          refreshKey={refreshKey}
                        />
                      </div>
                    </div>
                  );
                })}
              </ResponsiveGridLayout>
            );
          })()}
        </div>

        <ViewSelector
          visible={addModalVisible}
          onCancel={() => setAddModalVisible(false)}
          onOpenConfig={handleOpenConfig}
        />
        <ViewConfig
          open={configDrawerVisible}
          item={currentConfigItem}
          onConfirm={handleConfigConfirm}
          onClose={handleConfigClose}
        />
      </div>
    );
  }
);

Dashboard.displayName = 'Dashboard';

export default Dashboard;
