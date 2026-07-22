import React from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Form, TreeSelect } from 'antd';

interface MetricFieldSelectorFormItemProps {
  t: (key: string, defaultMessage?: string) => string;
  selectedDataSource: unknown;
  singleValueTreeData: any[];
  selectedField?: string;
  loadingSingleValueData: boolean;
  onFetchSingleValueDataFields: () => void;
  onSingleValueFieldChange: (checkedKeys: any) => void;
  validationMessage: string;
  readonly?: boolean;
}

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

export const MetricFieldSelectorFormItem: React.FC<
  MetricFieldSelectorFormItemProps
> = ({
  t,
  selectedDataSource,
  singleValueTreeData,
  selectedField,
  loadingSingleValueData,
  onFetchSingleValueDataFields,
  onSingleValueFieldChange,
  validationMessage,
  readonly = false,
}) => {
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

  const handleFieldSelect = (value: string | undefined) => {
    onSingleValueFieldChange(value ? [value] : []);
  };

  return (
    <Form.Item
      label={t('topology.nodeConfig.displayField')}
      name="selectedFields"
      rules={[
        {
          required: true,
          validator: (_, value) => {
            if (!value || value.length === 0) {
              return Promise.reject(new Error(validationMessage));
            }
            return Promise.resolve();
          },
        },
      ]}
    >
      <div className="flex items-start gap-3">
        <TreeSelect
          value={selectedField}
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
          onChange={(value) => handleFieldSelect(value as string | undefined)}
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
    </Form.Item>
  );
};
