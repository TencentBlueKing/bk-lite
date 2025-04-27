import React from 'react';
import { Form, Radio, Checkbox, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import {
  DataPermission,
  PermissionConfig,
  ModulePermissionConfig,
  ProviderPermissionConfig,
  ModuleContentProps,
  PermissionTypeSelectorProps,
  AllPermissionsSelectorProps,
  PermissionTableColumnsProps,
  SpecificDataTableProps
} from '@/app/system-manager/types/permission';
import { EDITABLE_MODULES } from '@/app/system-manager/constants/application';

const PermissionTypeSelector: React.FC<PermissionTypeSelectorProps> = ({
  type,
  module,
  subModule,
  handleTypeChange,
  isEditable
}) => {
  const { t } = useTranslation();
  return (
    <Form.Item label={t('system.permission.type')} className="mb-2">
      <Radio.Group
        value={type}
        onChange={(e) => handleTypeChange(e, module, subModule)}
        disabled={!isEditable}
      >
        <Radio value="all">{t('system.permission.allData')}</Radio>
        <Radio value="specific">{t('system.permission.specificData')}</Radio>
      </Radio.Group>
    </Form.Item>
  );
};

const AllPermissionsSelector: React.FC<AllPermissionsSelectorProps> = ({
  currentModule,
  module,
  subModule,
  handleAllPermissionChange,
  isEditable
}) => {
  const { t } = useTranslation();
  return (
    <Form.Item label={t('system.permission.permissions')} className="mt-4">
      <div className="flex space-x-4">
        <Checkbox
          checked={currentModule?.allPermissions?.view ?? true}
          onChange={(e) => handleAllPermissionChange(e, module, 'view', subModule)}
          disabled={!isEditable}
        >
          {t('system.permission.view')}
        </Checkbox>
        <Checkbox
          checked={currentModule?.allPermissions?.operate ?? true}
          disabled={!isEditable || !(currentModule?.allPermissions?.view ?? true)}
          onChange={(e) => handleAllPermissionChange(e, module, 'operate', subModule)}
        >
          {t('system.permission.operate')}
        </Checkbox>
      </div>
    </Form.Item>
  );
};

const PermissionTableColumns = ({
  handleSpecificDataChange,
  activeKey,
  activeSubModule
}: PermissionTableColumnsProps) => {
  const { t } = useTranslation();
  return [
    {
      title: t('system.permission.data'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('system.permission.actions'),
      key: 'actions',
      render: (_: unknown, record: DataPermission) => (
        <div className="flex space-x-4">
          <Checkbox
            checked={record.view}
            onChange={() => handleSpecificDataChange(
              { ...record, view: !record.view },
              activeKey,
              'view',
              activeKey === 'provider' ? activeSubModule : undefined
            )}
          >
            {t('system.permission.view')}
          </Checkbox>
          <Checkbox
            checked={record.operate}
            disabled={!record.view}
            onChange={() => handleSpecificDataChange(
              { ...record, operate: !record.operate },
              activeKey,
              'operate',
              activeKey === 'provider' ? activeSubModule : undefined
            )}
          >
            {t('system.permission.operate')}
          </Checkbox>
        </div>
      ),
    },
  ];
};

const SpecificDataTable: React.FC<SpecificDataTableProps> = ({
  isEditable,
  isModuleLoading,
  dataKey,
  moduleData,
  columns,
  pagination,
  handleTableChange,
  module,
  subModule,
  activeKey,
  activeSubModule,
  handleSpecificDataChange
}) => {
  const { t } = useTranslation();
  return (
    <Spin spinning={isModuleLoading}>
      {isEditable ? (
        <CustomTable
          rowKey="id"
          scroll={{ y: '300px' }}
          columns={columns}
          dataSource={moduleData[dataKey] || []}
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys: (moduleData[dataKey] || [])
              .filter(item => item.view)
              .map(item => item.id),
            onSelect: (record: DataPermission, selected: boolean) => {
              const newRecord = {
                ...record,
                view: selected,
                operate: selected ? record.operate : false
              };

              handleSpecificDataChange(
                newRecord,
                activeKey,
                'view',
                activeKey === 'provider' ? activeSubModule : undefined
              );
            },
            onSelectAll: (selected: boolean, selectedRows: DataPermission[], changeRows: DataPermission[]) => {
              changeRows.forEach(record => {
                const newRecord = {
                  ...record,
                  view: selected,
                  operate: selected ? record.operate : false
                };

                handleSpecificDataChange(
                  newRecord,
                  activeKey,
                  'view',
                  activeKey === 'provider' ? activeSubModule : undefined
                );
              });
            }
          }}
          pagination={{
            current: pagination.current || 1,
            pageSize: pagination.pageSize || 10,
            total: pagination.total || 0,
            onChange: (page: number, pageSize: number) => handleTableChange(
              { current: page, pageSize, total: pagination.total },
              {},
              {},
              module,
              subModule
            )
          }}
          className="mt-4"
        />
      ) : (
        <div className="text-gray-500 mt-4">{t('system.permission.noSpecificDataSupport')}</div>
      )}
    </Spin>
  );
};

const ModuleContent: React.FC<ModuleContentProps> = ({
  module,
  subModule,
  permissions,
  loading,
  moduleData,
  pagination,
  activeKey,
  activeSubModule,
  handleTypeChange,
  handleAllPermissionChange,
  handleSpecificDataChange,
  handleTableChange
}) => {
  let currentModule: PermissionConfig | undefined;

  if (subModule && module === 'provider') {
    const providerConfig = permissions[module] as ProviderPermissionConfig;
    currentModule = providerConfig[subModule] as PermissionConfig;
  } else {
    currentModule = permissions[module] as ModulePermissionConfig;
  }

  const type = currentModule?.type || 'all';
  const dataKey = subModule ? `${module}_${subModule}` : module;
  const isModuleLoading = loading[dataKey] || false;
  const isEditable = EDITABLE_MODULES.includes(subModule || module);

  const columns = PermissionTableColumns({
    handleSpecificDataChange,
    activeKey,
    activeSubModule
  });

  return (
    <div>
      <div className="mb-4">
        <PermissionTypeSelector
          type={type}
          module={module}
          subModule={subModule}
          handleTypeChange={handleTypeChange}
          isEditable={isEditable}
        />

        {type === 'all' ? (
          <AllPermissionsSelector
            currentModule={currentModule}
            module={module}
            subModule={subModule}
            handleAllPermissionChange={handleAllPermissionChange}
            isEditable={isEditable}
          />
        ) : (
          <SpecificDataTable
            isEditable={isEditable}
            isModuleLoading={isModuleLoading}
            dataKey={dataKey}
            moduleData={moduleData}
            columns={columns}
            pagination={pagination[dataKey] || { current: 1, pageSize: 10, total: 0 }}
            handleTableChange={handleTableChange}
            module={module}
            subModule={subModule}
            activeKey={activeKey}
            activeSubModule={activeSubModule}
            handleSpecificDataChange={handleSpecificDataChange}
          />
        )}
      </div>
    </div>
  );
};

export default ModuleContent;
export {
  PermissionTypeSelector,
  AllPermissionsSelector,
  PermissionTableColumns,
  SpecificDataTable
};
