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
  Select,
  Switch,
  TreeSelect,
  Tooltip,
} from 'antd';
import { ReloadOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import { getUnitCategories } from '@/app/ops-analysis/utils/unitFormat';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';

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

      <Form.Item label={t('topology.nodeConfig.unit')} name="unitId">
        <Select
          allowClear
          placeholder={t('common.selectMsg')}
          disabled={readonly}
          style={{ width: '200px' }}
          options={[
            { value: '', label: t('topology.nodeConfig.customSuffix') },
            ...getUnitCategories().map((cat) => ({
              label: cat.label,
              options: cat.units.map((u) => ({ value: u.id, label: u.label })),
            })),
          ]}
        />
      </Form.Item>

      {/* unitId 为空（自定义/未设）时回退到自由文本后缀，兼容旧配置 */}
      <Form.Item
        noStyle
        shouldUpdate={(prev, cur) => prev.unitId !== cur.unitId}
      >
        {({ getFieldValue }) =>
          !getFieldValue('unitId') ? (
            <Form.Item
              label={t('topology.nodeConfig.customSuffix')}
              name="unit"
            >
              <Input
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                style={{ width: '200px' }}
              />
            </Form.Item>
          ) : null
        }
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

      <ThresholdColorConfigSection
        t={t}
        thresholdColors={thresholdColors}
        onThresholdChange={onThresholdChange}
        onThresholdBlur={onThresholdBlur}
        onAddThreshold={onAddThreshold}
        onRemoveThreshold={onRemoveThreshold}
        readonly={readonly}
      />

      <Form.Item
        label={t('topology.nodeConfig.valueMappings')}
        name="valueMappings"
      >
        <ValueMappingsConfigSection t={t} readonly={readonly} />
      </Form.Item>
    </div>
  );
};
