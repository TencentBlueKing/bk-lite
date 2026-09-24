import React from 'react';
import { Form, Input, Radio, Tooltip } from 'antd';
import {
  AppstoreOutlined,
  ApartmentOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  FundOutlined,
  LineChartOutlined,
  NumberOutlined,
  OrderedListOutlined,
  PieChartOutlined,
  QuestionCircleOutlined,
  RadarChartOutlined,
  SortDescendingOutlined,
  SwapOutlined,
  TableOutlined,
} from '@ant-design/icons';
import type { ChartTypeItem } from '@/app/ops-analysis/constants/common';
import type {
  FilterBindings,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem, InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import { FilterBindingPanel } from '@/app/ops-analysis/components/unifiedFilter';
import {
  ConfigGroupTitle,
  ConfigSectionTitle,
} from '../configTitles';

const CHART_TYPE_CHIP =
  '!m-0 !inline-flex !h-8 !items-center !justify-center !rounded-md !px-2.5 !leading-none before:!hidden [&>span:last-child]:inline-flex [&>span:last-child]:h-full [&>span:last-child]:items-center [&>span:last-child]:gap-1.5 [&>span:last-child]:leading-none';

const getChartTypeIcon = (type: string) => {
  switch (type) {
    case 'line':
      return <LineChartOutlined />;
    case 'bar':
      return <BarChartOutlined />;
    case 'pie':
      return <PieChartOutlined />;
    case 'single':
      return <NumberOutlined />;
    case 'multiValue':
      return <AppstoreOutlined />;
    case 'gauge':
      return <DashboardOutlined />;
    case 'table':
      return <TableOutlined />;
    case 'eventTable':
      return <OrderedListOutlined />;
    case 'eventTimeline':
      return <ClockCircleOutlined />;
    case 'topN':
      return <SortDescendingOutlined />;
    case 'radar':
      return <RadarChartOutlined />;
    case 'cardList':
      return <AppstoreOutlined />;
    case 'topologyMap':
    case 'networkStatusTopology':
    case 'relatedTopology':
      return <ApartmentOutlined />;
    case 'room3D':
      return <FundOutlined />;
    default:
      return <LineChartOutlined />;
  }
};

interface WidgetDatasourceChartTypeFieldsProps {
  t: (key: string, defaultValue?: string) => string;
  selectedDataSource?: DatasourceItem;
  effectiveDataSource?: DatasourceItem;
  hasQueryParams: boolean;
  shouldShowUnifiedFilterSection: boolean;
  hasUnifiedFilterBindings: boolean;
  previewFilterDefinitions: UnifiedFilterDefinition[];
  filterBindings: FilterBindings;
  chartType: string;
  chartTypes: ChartTypeItem[];
  onFilterBindingsChange: (bindings: FilterBindings) => void;
  onChartTypeChange: (event: any) => void | Promise<void>;
  onOpenDataSourceSelector: () => void;
  onEditInputConfig: (param: ParamItem) => void;
  onParamOptionsResolved: (param: ParamItem, options: InputOption[]) => void;
  children?: React.ReactNode;
}

export const WidgetDatasourceChartTypeFields: React.FC<
  WidgetDatasourceChartTypeFieldsProps
> = ({
  t,
  selectedDataSource,
  effectiveDataSource,
  hasQueryParams,
  shouldShowUnifiedFilterSection,
  hasUnifiedFilterBindings,
  previewFilterDefinitions,
  filterBindings,
  chartType,
  chartTypes,
  onFilterBindingsChange,
  onChartTypeChange,
  onOpenDataSourceSelector,
  onEditInputConfig,
  onParamOptionsResolved,
  children,
}) => (
  <section>
    <ConfigSectionTitle>
      {t('dashboard.chartConfigSection', '图表配置')}
    </ConfigSectionTitle>

    <Form.Item
      label={t('dashboard.dataSource')}
      name="dataSource"
      rules={[{ required: true, message: t('common.selectTip') }]}
      getValueProps={() => ({
        value: selectedDataSource
          ? `${selectedDataSource.name}${
              selectedDataSource.rest_api
                ? `（${selectedDataSource.rest_api}）`
                : ''
            }`
          : '',
      })}
    >
      <Input
        readOnly
        placeholder={t('common.selectTip')}
        suffix={
          <SwapOutlined
            className="cursor-pointer text-(--color-primary)"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onOpenDataSourceSelector();
            }}
          />
        }
        onClick={() => onOpenDataSourceSelector()}
        className="cursor-pointer"
      />
    </Form.Item>

    <Form.Item
      label={t('dashboard.chartTypeLabel')}
      name="chartType"
      rules={[{ required: true, message: t('common.selectTip') }]}
      initialValue={chartTypes[0]?.value}
      className="!mb-5"
    >
      <Radio.Group
        value={chartType}
        onChange={onChartTypeChange}
        className="flex flex-wrap gap-2"
      >
        {chartTypes.map((item: ChartTypeItem) => {
          const isSelected = chartType === item.value;
          return (
            <Radio.Button
              key={item.value}
              value={item.value}
              className={`${CHART_TYPE_CHIP} ${
                isSelected
                  ? '!border-(--color-primary) !bg-(--color-primary-bg-active) !text-(--color-primary)'
                  : '!border-transparent !bg-(--color-fill-2) !text-(--color-text-2) hover:!text-(--color-text-1)'
              }`}
            >
              <span className="inline-flex items-center gap-1.5 leading-none">
                <span className="flex h-3.5 w-3.5 items-center justify-center text-[13px] leading-none">
                  {getChartTypeIcon(item.value)}
                </span>
                <span className="text-xs leading-none">{t(item.label)}</span>
              </span>
            </Radio.Button>
          );
        })}
      </Radio.Group>
    </Form.Item>

    {hasQueryParams ? (
      <div className="mb-6">
        <ConfigGroupTitle>
          {t('dashboard.queryParams')}
        </ConfigGroupTitle>
        <DataSourceParamsConfig
          selectedDataSource={effectiveDataSource}
          includeFilterTypes={['params', 'fixed']}
          onEditInputConfig={onEditInputConfig}
          onParamOptionsResolved={(param, options) =>
            onParamOptionsResolved(param, options)
          }
        />
      </div>
    ) : null}

    {shouldShowUnifiedFilterSection && hasUnifiedFilterBindings ? (
      <div className="mb-6">
        <ConfigGroupTitle
          extra={
            <Tooltip
              title={
                <span className="whitespace-pre-line">
                  {t('dashboard.unifiedFilterBindingTip')}
                </span>
              }
              overlayInnerStyle={{ maxWidth: 480, width: 480 }}
              styles={{ body: { maxWidth: 480, width: 480 } }}
            >
              <QuestionCircleOutlined className="cursor-help text-(--color-text-3)" />
            </Tooltip>
          }
        >
          {t('dashboard.unifiedFilterLinkage')}
        </ConfigGroupTitle>
        <FilterBindingPanel
          definitions={previewFilterDefinitions}
          dataSourceParams={selectedDataSource!.params}
          filterBindings={filterBindings}
          onChange={onFilterBindingsChange}
        />
      </div>
    ) : null}

    {children}
  </section>
);
