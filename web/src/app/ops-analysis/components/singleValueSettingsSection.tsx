/**
 * 共享单值配置 UI Section
 * 供仪表盘 ViewConfig 和拓扑 NodeConfPanel 复用
 */
import React from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  ColorPicker,
  Switch,
  TreeSelect,
  Tooltip,
} from 'antd';
import {
  PlusCircleOutlined,
  MinusCircleOutlined,
  ReloadOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';

/** Switch + Tooltip 包装：透传 Form.Item 注入的 checked/onChange，同时支持 hover 提示 */
const TooltipSwitch: React.FC<{
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  tooltipTitle?: string;
}> = ({ checked, onChange, disabled, tooltipTitle }) => {
  const switchEl = (
    <Switch checked={checked} onChange={onChange} disabled={disabled} />
  );
  if (tooltipTitle) {
    return (
      <Tooltip title={tooltipTitle}>
        <span className="inline-flex">{switchEl}</span>
      </Tooltip>
    );
  }
  return switchEl;
};

interface SingleValueSettingsSectionProps {
  t: (key: string) => string;
  sectionTitle?: string;
  selectedDataSource: any;
  singleValueTreeData: any[];
  selectedFields: string[];
  loadingSingleValueData: boolean;
  thresholdColors: ThresholdColorConfig[];
  onFetchSingleValueDataFields: () => void;
  onSingleValueFieldChange: (checkedKeys: any) => void;
  onThresholdChange: (
    index: number,
    field: 'value' | 'color',
    value: string | number,
  ) => void;
  onThresholdBlur: (index: number, value: number | null) => void;
  onAddThreshold: (afterIndex?: number) => void;
  onRemoveThreshold: (index: number) => void;
  compareAvailable: boolean;
  /** 是否只读模式 */
  readonly?: boolean;
}

export const SingleValueSettingsSection: React.FC<
  SingleValueSettingsSectionProps
> = ({
  t,
  sectionTitle,
  selectedDataSource,
  singleValueTreeData,
  selectedFields,
  loadingSingleValueData,
  thresholdColors,
  onFetchSingleValueDataFields,
  onSingleValueFieldChange,
  onThresholdChange,
  onThresholdBlur,
  onAddThreshold,
  onRemoveThreshold,
  compareAvailable,
  readonly = false,
}) => {
  const resolvedSectionTitle =
    sectionTitle || t('topology.nodeConfig.dataSettings');
  const canSelectField =
    Boolean(selectedDataSource) && singleValueTreeData.length > 0 && !readonly;
  const fieldSelectorDisabled =
    !selectedDataSource || readonly || loadingSingleValueData;
  const hasNestedFieldOptions = singleValueTreeData.some(
    (node) => node.children?.length,
  );
  const fieldSelectorClassName = canSelectField
    ? '[&_.ant-select-selector]:cursor-pointer'
    : '';
  const fieldPopupClassName = hasNestedFieldOptions
    ? ''
    : '[&_.ant-select-tree-switcher]:hidden [&_.ant-select-tree-switcher]:!w-0 [&_.ant-select-tree-indent]:hidden';

  const getNodeTitleText = (title: any): string => {
    if (typeof title === 'string' || typeof title === 'number') {
      return String(title);
    }

    if (Array.isArray(title)) {
      return title.map(getNodeTitleText).join('');
    }

    if (React.isValidElement<{ children?: React.ReactNode }>(title)) {
      return getNodeTitleText(title.props.children);
    }

    return '';
  };

  const buildFieldOptions = (nodes: any[]): any[] => {
    return nodes.map((node) => ({
      title: node.title,
      value: node.key,
      key: node.key,
      selectable: Boolean(node.isLeaf),
      searchText: `${node.key} ${getNodeTitleText(node.title)}`.toLowerCase(),
      children: node.children ? buildFieldOptions(node.children) : undefined,
    }));
  };

  const handleFieldSelect = (value: string | undefined) => {
    onSingleValueFieldChange(value ? [value] : []);
  };

  return (
    <div className="mb-6">
      <div className="mb-6">
        <div className="font-medium mb-4">{resolvedSectionTitle}</div>

        <Form.Item
          label={t('topology.nodeConfig.displayField')}
          name="selectedFields"
          rules={[
            {
              required: true,
              validator: (_, value) => {
                if (!value || value.length === 0) {
                  return Promise.reject(
                    new Error(t('topology.nodeConfig.selectAtLeastOneField')),
                  );
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <div>
            <div className="flex items-start gap-3">
              <TreeSelect
                value={selectedFields[0]}
                treeData={buildFieldOptions(singleValueTreeData)}
                treeDefaultExpandAll
                allowClear
                showSearch
                treeNodeFilterProp="searchText"
                placeholder={
                  !selectedDataSource
                    ? t('topology.nodeConfig.selectDataSourceFirst')
                    : loadingSingleValueData
                      ? t('topology.nodeConfig.fetchingDataFields')
                      : singleValueTreeData.length === 0
                        ? t('topology.nodeConfig.clickRefreshToGetFields')
                        : t('topology.nodeConfig.selectDisplayField')
                }
                disabled={fieldSelectorDisabled}
                onChange={(value) =>
                  handleFieldSelect(value as string | undefined)
                }
                className={fieldSelectorClassName}
                popupClassName={fieldPopupClassName}
                style={{ width: '100%' }}
                dropdownStyle={{ maxHeight: 360, overflow: 'auto' }}
              />
              <Button
                type="text"
                icon={<ReloadOutlined />}
                onClick={onFetchSingleValueDataFields}
                loading={loadingSingleValueData}
                disabled={!selectedDataSource || readonly}
                title={t('topology.nodeConfig.refreshDataFields')}
                className="shrink-0"
              />
            </div>
          </div>
        </Form.Item>
      </div>

      <Form.Item
        label={
          <span>
            {t('dashboard.compareLabel')}
            <Tooltip title={t('dashboard.comparePreviousPeriodTip')}>
              <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
            </Tooltip>
          </span>
        }
        name="compare"
        valuePropName="checked"
      >
        <TooltipSwitch
          disabled={readonly || !compareAvailable}
          tooltipTitle={
            !readonly && !compareAvailable
              ? t('dashboard.compareUnavailableTip')
              : undefined
          }
        />
      </Form.Item>

      <Form.Item label={t('topology.nodeConfig.unit')} name="unit">
        <Input
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          style={{ width: '200px' }}
        />
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.conversionFactor')}
        name="conversionFactor"
      >
        <InputNumber
          min={0}
          max={100000}
          step={0.01}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          style={{ width: '120px' }}
        />
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.decimalPlaces')}
        name="decimalPlaces"
      >
        <InputNumber
          min={0}
          max={10}
          step={1}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          style={{ width: '120px' }}
        />
      </Form.Item>

      <Form.Item label={t('topology.nodeConfig.thresholdColors')}>
        <div className="rounded-md border border-(--color-border-1) bg-(--color-fill-1) px-3 py-2">
          {thresholdColors.map((threshold, index) => {
            const isBaseThreshold = index === thresholdColors.length - 1;
            return (
              <div key={index} className="flex items-center gap-2 py-1.5">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-600 whitespace-nowrap">
                    {t('topology.nodeConfig.thresholdWhenValueGte')}
                  </span>
                  <InputNumber
                    value={parseFloat(threshold.value)}
                    onChange={(value) =>
                      onThresholdChange(index, 'value', value || 0)
                    }
                    onBlur={(e) => {
                      if (!isBaseThreshold && !readonly) {
                        const value = parseFloat(e.target.value);
                        onThresholdBlur(index, isNaN(value) ? 0 : value);
                      }
                    }}
                    placeholder={t('common.inputMsg')}
                    disabled={isBaseThreshold || readonly}
                    style={{ width: '100px' }}
                    size="small"
                    min={0}
                  />
                  <span className="text-sm text-gray-600">
                    {t('topology.nodeConfig.thresholdShow')}
                  </span>
                </div>
                <ColorPicker
                  value={threshold.color}
                  onChange={(color) =>
                    onThresholdChange(index, 'color', color.toHexString())
                  }
                  disabled={readonly}
                  size="small"
                  showText
                />
                <div className="flex items-center gap-2 pl-3">
                  {!readonly && (
                    <span
                      onClick={() => onAddThreshold(index)}
                      className="cursor-pointer text-(--color-text-2) hover:text-(--color-primary) transition-colors duration-200"
                      style={{ fontSize: '14px' }}
                      title={t('topology.nodeConfig.addThresholdBelow')}
                    >
                      <PlusCircleOutlined />
                    </span>
                  )}
                  {!readonly && (
                    <span
                      onClick={
                        isBaseThreshold
                          ? undefined
                          : () => onRemoveThreshold(index)
                      }
                      className={`transition-colors duration-200 ${
                        isBaseThreshold
                          ? 'text-(--color-text-4) cursor-not-allowed'
                          : 'cursor-pointer text-(--color-text-2) hover:text-(--color-primary)'
                      }`}
                      style={{ fontSize: '14px' }}
                      title={
                        isBaseThreshold
                          ? t('topology.nodeConfig.baseThresholdNotRemovable')
                          : t('topology.nodeConfig.removeThreshold')
                      }
                    >
                      <MinusCircleOutlined />
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Form.Item>
    </div>
  );
};
