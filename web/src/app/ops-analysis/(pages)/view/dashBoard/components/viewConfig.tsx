import React, { useEffect } from 'react';
import { useTranslation } from '@/utils/i18n';
import { ViewConfigProps } from '@/app/ops-analysis/types/dashBoard';
import { Drawer, Button, Form, Input, Radio } from 'antd';
import { ViewConfigItem } from '@/app/ops-analysis/types/dashBoard';
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
import {
  getChartTypeList,
  ChartTypeItem,
} from '@/app/ops-analysis/constants/common';
import DataSourceParamsConfig from '@/app/ops-analysis/components/paramsConfig';
import DataSourceSelect from '@/app/ops-analysis/components/dataSourceSelect';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  dataSource: string | number;
  dataSourceParams?: any[];
  params?: Record<string, any>;
}

interface ViewConfigPropsWithManager extends ViewConfigProps {
  dataSourceManager: ReturnType<typeof useDataSourceManager>;
}

const ViewConfig: React.FC<ViewConfigPropsWithManager> = ({
  open,
  item: widgetItem,
  onConfirm,
  onClose,
  dataSourceManager,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const {
    dataSources,
    selectedDataSource,
    setSelectedDataSource,
    findDataSource,
    setDefaultParamValues,
    restoreUserParamValues,
    processFormParamsForSubmit,
  } = dataSourceManager;

  const getFilteredChartTypes = (
    dataSource: DatasourceItem | undefined
  ): ChartTypeItem[] => {
    if (!dataSource?.chart_type?.length) {
      return [];
    }

    const allChartTypes = getChartTypeList();
    return dataSource.chart_type
      .map((type: string) =>
        allChartTypes.find((chart) => chart.value === type)
      )
      .filter((item): item is ChartTypeItem => Boolean(item))
      .filter((item: ChartTypeItem) => item.value !== 'single');
  };

  const getDataSourceChartTypes = React.useMemo(() => {
    return getFilteredChartTypes(selectedDataSource);
  }, [selectedDataSource]);

  const initializeItemForm = (widgetItem: ViewConfigItem): void => {
    const { valueConfig } = widgetItem;
    const formValues: FormValues = {
      name: widgetItem?.name || '',
      description: widgetItem.description || '',
      chartType: valueConfig?.chartType || '',
      dataSource: valueConfig?.dataSource || '',
      dataSourceParams: valueConfig?.dataSourceParams || [],
      params: {},
    };
    if (!formValues) return;

    const targetDataSource = findDataSource(formValues.dataSource);
    if (targetDataSource) {
      setSelectedDataSource(targetDataSource);
      formValues.params = formValues.params || {};

      // 如果没有指定图表类型，使用数据源支持的第一个图表类型（排除单值）
      if (!formValues.chartType && targetDataSource.chart_type?.length) {
        const availableChartTypes = getFilteredChartTypes(targetDataSource);
        formValues.chartType = availableChartTypes[0]?.value;
      }

      if (targetDataSource.params?.length) {
        setDefaultParamValues(targetDataSource.params, formValues.params);
        if (formValues.dataSourceParams?.length) {
          restoreUserParamValues(
            formValues.dataSourceParams,
            formValues.params
          );
        }
      }
    } else {
      setSelectedDataSource(undefined);
    }

    form.setFieldsValue(formValues);
  };

  const resetForm = (): void => {
    form.resetFields();
    setSelectedDataSource(undefined);
  };

  useEffect(() => {
    if (open && dataSources.length > 0) {
      initializeItemForm(widgetItem);
    } else if (!open) {
      resetForm();
    }
  }, [open, widgetItem, form, dataSources]);

  const handleConfirm = async () => {
    try {
      const values: FormValues = await form.validateFields();
      if (values.params && selectedDataSource?.params) {
        values.dataSourceParams = processFormParamsForSubmit(
          values.params,
          selectedDataSource.params
        );
        delete values.params;
      }

      onConfirm?.(values);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  return (
    <Drawer
      title={t('dashboard.viewConfig')}
      placement="right"
      width={600}
      open={open}
      onClose={onClose}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button type="primary" onClick={handleConfirm}>
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={onClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form form={form} labelCol={{ span: 4 }}>
        <div className="mb-6">
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('dashboard.basicSettings')}
          </div>
          <Form.Item
            label={t('dashboard.widgetName')}
            name="name"
            rules={[{ required: true, message: t('dashboard.inputName') }]}
          >
            <Input placeholder={t('dashboard.inputName')} />
          </Form.Item>
          <Form.Item label={t('dataSource.describe')} name="description">
            <Input.TextArea
              placeholder={t('common.inputMsg')}
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </Form.Item>
        </div>

        <div className="mb-6">
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('dashboard.dataSource')}
          </div>
          <Form.Item
            label={t('dashboard.dataSourceType')}
            name="dataSource"
            rules={[{ required: true, message: t('common.selectTip') }]}
          >
            <DataSourceSelect
              placeholder={t('common.selectTip')}
              dataSources={dataSources}
              disabled
              onDataSourceChange={setSelectedDataSource}
            />
          </Form.Item>
        </div>

        <div className="mb-6">
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('dashboard.paramSettings')}
          </div>
          <DataSourceParamsConfig
            selectedDataSource={selectedDataSource}
            includeFilterTypes={['params', 'fixed']}
          />
        </div>

        <div className="mb-6">
          <div className="font-bold text-[var(--color-text-1)] mb-4">
            {t('dashboard.chartTypeLabel')}
          </div>
          <Form.Item
            label={t('dashboard.chartTypeLabel')}
            name="chartType"
            rules={[{ required: true, message: t('common.selectTip') }]}
            initialValue={getDataSourceChartTypes[0]?.value}
          >
            <Radio.Group>
              {getDataSourceChartTypes.map((item: ChartTypeItem) => (
                <Radio.Button key={item.value} value={item.value}>
                  {t(item.label)}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Form.Item>
        </div>
      </Form>
    </Drawer>
  );
};

export default ViewConfig;
