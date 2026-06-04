import React from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Radio, TreeSelect } from 'antd';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';

interface GaugeSettingsSectionProps {
  t: (key: string, defaultMessage?: string) => string;
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
}

export const GaugeSettingsSection: React.FC<GaugeSettingsSectionProps> = ({
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
}) => {
  const resolvedSectionTitle = sectionTitle || t('dashboard.gaugeSettings');
  const canSelectField =
    Boolean(selectedDataSource) && singleValueTreeData.length > 0;
  const fieldSelectorDisabled = !selectedDataSource || loadingSingleValueData;
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
                    new Error(t('topology.nodeConfig.selectDisplayField')),
                  );
                }
                return Promise.resolve();
              },
            },
          ]}
        >
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
              disabled={!selectedDataSource}
              title={t('topology.nodeConfig.refreshDataFields')}
              className="shrink-0"
            />
          </div>
        </Form.Item>

        <Form.Item
          label={t('dashboard.gaugeMin')}
          name="gaugeMin"
          rules={[
            {
              required: true,
              message: t('common.inputMsg'),
            },
          ]}
          initialValue={0}
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          label={t('dashboard.gaugeMax')}
          name="gaugeMax"
          rules={[
            {
              required: true,
              message: t('common.inputMsg'),
            },
            ({ getFieldValue }) => ({
              validator(_, value) {
                const min = Number(getFieldValue('gaugeMin'));
                const max = Number(value);
                if (
                  !Number.isFinite(min) ||
                  !Number.isFinite(max) ||
                  max <= min
                ) {
                  return Promise.reject(
                    new Error(t('dashboard.gaugeMaxMustGreaterMin')),
                  );
                }
                return Promise.resolve();
              },
            }),
          ]}
          initialValue={100}
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          label={t('dashboard.gaugeShape')}
          name="gaugeShape"
          initialValue="semicircle"
        >
          <Radio.Group>
            <Radio.Button value="semicircle">
              {t('dashboard.gaugeShapeSemicircle')}
            </Radio.Button>
            <Radio.Button value="circle">
              {t('dashboard.gaugeShapeCircle')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        <Form.Item label={t('topology.nodeConfig.unit')} name="unit">
          <Input
            placeholder={t('common.inputMsg')}
            style={{ width: '240px' }}
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
            style={{ width: '140px' }}
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
            style={{ width: '140px' }}
          />
        </Form.Item>

        <ThresholdColorConfigSection
          t={t}
          thresholdColors={thresholdColors}
          onThresholdChange={onThresholdChange}
          onThresholdBlur={onThresholdBlur}
          onAddThreshold={onAddThreshold}
          onRemoveThreshold={onRemoveThreshold}
        />
      </div>
    </div>
  );
};
