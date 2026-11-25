import React from 'react';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { Form, Input, Select, Tooltip, TreeSelect, type TreeSelectProps } from 'antd';
import {
  SCALAR_CALC_METHODS,
  type ScalarCalcMethod,
} from '@/app/ops-analysis/utils/scalarReduction';

type Translate = (key: string) => string;

const METHOD_LABEL_KEY: Record<ScalarCalcMethod, string> = {
  count: 'dashboard.calcCount',
  avg: 'dashboard.calcAvg',
  max: 'dashboard.calcMax',
  min: 'dashboard.calcMin',
  sum: 'dashboard.calcSum',
  latest: 'dashboard.calcLatest',
};

export const ScalarCalcMethodItem: React.FC<{
  t: Translate;
  disabled?: boolean;
}> = ({ t, disabled = false }) => (
  <Form.Item
    name="scalarCalcMethod"
    label={(
      <span>
        {t('dashboard.calcMethod')}
        <Tooltip title={t('dashboard.calcMethodTip')} styles={{ body: { maxWidth: 360 } }}>
          <QuestionCircleOutlined className="ml-1 text-(--color-text-3) cursor-help" />
        </Tooltip>
      </span>
    )}
  >
    <Select
      allowClear
      disabled={disabled}
      placeholder={t('dashboard.calcMethodNone')}
      data-testid="scalar-calc-method"
      options={SCALAR_CALC_METHODS.map((method) => ({
        value: method,
        label: t(METHOD_LABEL_KEY[method]),
      }))}
    />
  </Form.Item>
);

export const ScalarCalcTimeFieldItem: React.FC<{
  t: Translate;
  disabled?: boolean;
  treeData: NonNullable<TreeSelectProps['treeData']>;
  className?: string;
  popupClassName?: string;
  placeholder: string;
}> = ({
  t,
  disabled = false,
  treeData,
  className,
  popupClassName,
  placeholder,
}) => {
  const method = Form.useWatch('scalarCalcMethod');
  if (method !== 'latest') {
    return (
      <Form.Item name="scalarCalcTimeField" hidden preserve>
        <Input />
      </Form.Item>
    );
  }
  return (
    <Form.Item
      name="scalarCalcTimeField"
      label={(
        <span>
          {t('dashboard.calcTimeField')}
          <Tooltip title={t('dashboard.calcTimeFieldTip')} styles={{ body: { maxWidth: 360 } }}>
            <QuestionCircleOutlined className="ml-1 text-(--color-text-3) cursor-help" />
          </Tooltip>
        </span>
      )}
      rules={[
        {
          required: true,
          validator: (_, value) => {
            if (typeof value === 'string' && value.trim()) return Promise.resolve();
            return Promise.reject(new Error(t('dashboard.calcTimeFieldRequired')));
          },
        },
      ]}
    >
      <TreeSelect
        treeData={treeData}
        treeDefaultExpandAll
        allowClear
        showSearch
        treeNodeFilterProp="searchText"
        placeholder={placeholder}
        disabled={disabled}
        className={className}
        classNames={popupClassName ? { popup: { root: popupClassName } } : undefined}
        styles={{ popup: { root: { maxHeight: 360, overflow: 'auto' } } }}
      />
    </Form.Item>
  );
};
