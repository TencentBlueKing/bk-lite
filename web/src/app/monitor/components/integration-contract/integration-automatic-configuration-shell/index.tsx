import React from 'react';
import { Form, Button, Spin, Dropdown } from 'antd';
import type { FormInstance, FormItemProps, MenuProps } from 'antd';
import { DownOutlined, UploadOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import Permission from '@/components/permission';
import SectionHeader from '@/components/section-header';
import CustomTable from '@/components/custom-table';

type CustomTableProps = React.ComponentProps<typeof CustomTable>;

interface IntegrationAutomaticConfigurationShellProps {
  form: FormInstance;
  loading?: boolean;
  emptyState?: {
    description: React.ReactNode;
    minHeight?: string;
  };
  configurationTitle: React.ReactNode;
  basicInformationTitle?: React.ReactNode;
  formItems?: React.ReactNode;
  formItemsWrapperClassName?: string;
  tableSectionClassName?: string;
  monitoredObjectTitle: React.ReactNode;
  importButtonLabel: React.ReactNode;
  onImport: () => void;
  batchOperationLabel: React.ReactNode;
  batchMenuItems: MenuProps['items'];
  onBatchMenuClick: MenuProps['onClick'];
  batchDisabled: boolean;
  tableFieldName: string;
  tableFieldRules?: FormItemProps['rules'];
  tableNode?: React.ReactNode;
  tableDataSource?: CustomTableProps['dataSource'];
  tableColumns?: CustomTableProps['columns'];
  tableRowKey?: CustomTableProps['rowKey'];
  tablePagination?: CustomTableProps['pagination'];
  tableRowSelection?: CustomTableProps['rowSelection'];
  tableScroll?: CustomTableProps['scroll'];
  tableLoading?: boolean;
  tableProps?: Omit<
    CustomTableProps,
    | 'dataSource'
    | 'columns'
    | 'rowKey'
    | 'pagination'
    | 'rowSelection'
    | 'scroll'
    | 'loading'
  >;
  confirmButtonLabel: React.ReactNode;
  confirmLoading?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  permissionRequired?: string[] | null;
  secondaryActions?: React.ReactNode;
  actionsWrapperClassName?: string;
  children?: React.ReactNode;
}

const IntegrationAutomaticConfigurationShell: React.FC<
  IntegrationAutomaticConfigurationShellProps
> = ({
  form,
  loading = false,
  emptyState,
  configurationTitle,
  basicInformationTitle,
  formItems,
  formItemsWrapperClassName,
  tableSectionClassName,
  monitoredObjectTitle,
  importButtonLabel,
  onImport,
  batchOperationLabel,
  batchMenuItems,
  onBatchMenuClick,
  batchDisabled,
  tableFieldName,
  tableFieldRules,
  tableNode,
  tableDataSource,
  tableColumns,
  tableRowKey,
  tablePagination,
  tableRowSelection,
  tableScroll,
  tableLoading = false,
  tableProps,
  confirmButtonLabel,
  confirmLoading = false,
  confirmDisabled = false,
  onConfirm,
  permissionRequired = ['Add'],
  secondaryActions,
  actionsWrapperClassName,
  children,
}) => {
  const confirmButton = (
    <Button
      type="primary"
      loading={confirmLoading}
      disabled={confirmDisabled}
      onClick={onConfirm}
    >
      {confirmButtonLabel}
    </Button>
  );

  const wrappedConfirmButton = permissionRequired ? (
    <Permission requiredPermissions={permissionRequired}>
      {confirmButton}
    </Permission>
  ) : (
    confirmButton
  );

  const resolvedTableNode = tableNode ?? (
    <CustomTable
      {...tableProps}
      dataSource={tableDataSource}
      columns={tableColumns}
      rowKey={tableRowKey}
      pagination={tablePagination}
      rowSelection={tableRowSelection}
      scroll={tableScroll}
      loading={tableLoading}
    />
  );

  return (
    <Spin spinning={loading}>
      <div className="px-[10px]">
        {emptyState ? (
          <div
            className="flex items-center justify-center"
            style={{ minHeight: emptyState.minHeight || '400px' }}
          >
            <CompactEmptyState description={emptyState.description} className="py-8" />
          </div>
        ) : (
          <Form form={form} name="basic" layout="vertical">
            <SectionHeader
              className="mb-[10px] ml-[-10px]"
              title={configurationTitle}
              titleClassName="m-0 text-[14px] font-semibold text-[var(--color-text-1)]"
            />
            {formItems ? (
              <div className={formItemsWrapperClassName}>{formItems}</div>
            ) : null}
            {basicInformationTitle ? (
              <SectionHeader
                className="mb-[10px] ml-[-10px]"
                title={basicInformationTitle}
                titleClassName="m-0 text-[14px] font-semibold text-[var(--color-text-1)]"
              />
            ) : null}
            <div className={tableSectionClassName}>
              <SectionHeader
                className="mb-[10px]"
                title={(
                  <>
                    {monitoredObjectTitle}
                    <span
                      className="ml-[4px] align-middle text-[14px] text-[#ff4d4f]"
                      style={{ fontFamily: 'SimSun, sans-serif' }}
                    >
                      *
                    </span>
                  </>
                )}
                titleClassName="m-0 text-[14px] font-normal text-[var(--color-text-1)]"
                actions={(
                  <div className="flex gap-[8px]">
                    <Button
                      icon={<UploadOutlined />}
                      type="primary"
                      onClick={onImport}
                    >
                      {importButtonLabel}
                    </Button>
                    <Dropdown
                      menu={{
                        items: batchMenuItems,
                        onClick: onBatchMenuClick,
                      }}
                      disabled={batchDisabled}
                    >
                      <Button>
                        {batchOperationLabel}
                        <DownOutlined className="ml-[4px]" />
                      </Button>
                    </Dropdown>
                  </div>
                )}
              />
              <Form.Item name={tableFieldName} rules={tableFieldRules}>
                {resolvedTableNode}
              </Form.Item>
            </div>
            <Form.Item className={actionsWrapperClassName}>
              <div className="flex gap-[10px]">
                {wrappedConfirmButton}
                {secondaryActions}
              </div>
            </Form.Item>
          </Form>
        )}
      </div>
      {children}
    </Spin>
  );
};

export default IntegrationAutomaticConfigurationShell;
