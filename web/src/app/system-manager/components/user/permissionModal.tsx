import React, { useEffect, useState } from 'react';
import { Form, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useClientData } from '@/context/client';
import OperateModal from '@/components/operate-modal';
import CustomTable from '@/components/custom-table';
import { useRoleApi } from '@/app/system-manager/api/application';
import {
  AppPermission,
  PermissionModalProps,
  PermissionFormValues,
  DataPermission as PermissionDataType
} from '@/app/system-manager/types/permission';

const PermissionModal: React.FC<PermissionModalProps> = ({ visible, rules = {}, node, onOk, onCancel }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<PermissionFormValues>();
  const { clientData } = useClientData();
  const { getGroupDataRule } = useRoleApi();

  const [appDataPermissions, setAppDataPermissions] = useState<{ [key: string]: PermissionDataType[] }>({});
  const [appData, setAppData] = useState<AppPermission[]>([]);
  const [appLoadingStates, setAppLoadingStates] = useState<{ [key: string]: boolean }>({});

  const clientModules = clientData.filter(client => client.name !== 'ops-console').map(r=> r.name);

  useEffect(() => {
    if (visible && node) {
      fetchAllAppDataRules();
      form.setFieldsValue({
        groupName: typeof node?.title === 'string' ? node.title : ''
      });

      const newAppData = clientModules.map((item, index) => {
        let permission = 0;
        const ruleValue = rules[item];
        
        if (Array.isArray(ruleValue)) {
          permission = ruleValue.find(val => val !== 0) || 0;
        } else if (typeof ruleValue === 'number') {
          permission = ruleValue;
        } else {
          permission = 0;
        }
        
        
        return {
          key: index.toString(),
          app: item,
          permission: permission,
        };
      });
      
      setAppData(newAppData);
    }
  }, [visible, node, rules]);

  const fetchAllAppDataRules = async () => {
    if (!node?.key) return;

    const initialLoadingStates = clientModules.reduce((acc, app) => {
      acc[app] = true;
      return acc;
    }, {} as { [key: string]: boolean });
    setAppLoadingStates(initialLoadingStates);

    try {
      const allData = await getGroupDataRule({
        params: { 
          group_id: node.key.toString()
        }
      });

      const groupedPermissions: { [key: string]: PermissionDataType[] } = {};
      
      clientModules.forEach(app => {
        groupedPermissions[app] = [];
      });

      if (allData && Array.isArray(allData)) {
        allData.forEach((permission: PermissionDataType) => {
          if (permission.app && groupedPermissions[permission.app]) {
            groupedPermissions[permission.app].push(permission);
          }
        });
      }

      setAppDataPermissions(groupedPermissions);
    } catch (error) {
      console.error('Failed to fetch group data rules:', error);
      const emptyPermissions = clientModules.reduce((acc, app) => {
        acc[app] = [];
        return acc;
      }, {} as { [key: string]: PermissionDataType[] });
      setAppDataPermissions(emptyPermissions);
    } finally {
      const clearedLoadingStates = clientModules.reduce((acc, app) => {
        acc[app] = false;
        return acc;
      }, {} as { [key: string]: boolean });
      setAppLoadingStates(clearedLoadingStates);
    }
  };

  const columns = [
    {
      title: t('system.permission.app'),
      dataIndex: 'app',
      key: 'app',
      width: 150,
    },
    {
      title: t('system.permission.dataPermission'),
      dataIndex: 'permission',
      key: 'permission',
      render: (_text: unknown, record: AppPermission, index: number) => {
        const options = [
          { value: 0, label: t('system.permission.fullPermission') }
        ];
        
        const currentAppPermissions = appDataPermissions[record.app] || [];
        if (currentAppPermissions.length > 0) {
          currentAppPermissions.forEach(permission => {
            options.push({ value: Number(permission.id), label: permission.name });
          });
        }

        const isAppLoading = appLoadingStates[record.app] || false;
        
        const currentPermission = appData[index]?.permission ?? 0;
        

        return (
          <Select
            key={`${record.app}-${currentPermission}`}
            value={currentPermission}
            className="w-full"
            options={options}
            loading={isAppLoading}
            disabled={isAppLoading}
            placeholder={t('common.select')}
            onChange={(value: number) => {
              setAppData(prevData => {
                const newData = [...prevData];
                if (newData[index]) {
                  newData[index] = { ...newData[index], permission: value };
                }
                return newData;
              });
            }}
          />
        );
      },
    },
  ];

  const isAnyAppLoading = Object.values(appLoadingStates).some(loading => loading);

  const handleOk = () => {
    form.validateFields().then((values: PermissionFormValues) => {
      onOk({ ...values, permissions: appData });
    });
  };

  return (
    <OperateModal
      title={t('system.permission.setDataPermission')}
      open={visible}
      onOk={handleOk}
      onCancel={() => {
        form.resetFields();
        setAppData([]);
        setAppDataPermissions({});
        setAppLoadingStates({});
        onCancel();
      }}
      confirmLoading={isAnyAppLoading}
    >
      <Form
        form={form}
        layout="vertical"
      >
        <Form.Item
          name="groupName"
          label={t('system.permission.group')}
          rules={[{ required: true, message: t('system.permission.pleaseInputGroupName') }]}
        >
          <Input disabled />
        </Form.Item>
        <Form.Item label={t('system.permission.dataPermission')}>
          <CustomTable
            columns={columns}
            dataSource={appData}
            pagination={false}
            size="small"
            rowKey="key"
            bordered={false}
            loading={isAnyAppLoading}
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default PermissionModal;
