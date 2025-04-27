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

const PermissionModal: React.FC<PermissionModalProps> = ({ visible, rules = [], node, onOk, onCancel }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<PermissionFormValues>();
  const { clientData } = useClientData();
  const { getGroupDataRule } = useRoleApi();

  const [dataPermissions, setDataPermissions] = useState<PermissionDataType[]>([]);
  const [appData, setAppData] = useState<AppPermission[]>([]);

  const clientModules = clientData.filter(client => client.client_id !== 'ops-console').map(r=> r.client_id);

  useEffect(() => {
    if (visible && node) {
      fetchGroupDataRule();
      form.setFieldsValue({
        groupName: typeof node?.title === 'string' ? node.title : ''
      });

      setAppData(
        clientModules.map((item, index) => ({
          key: index.toString(),
          app: item,
          permission: item === 'opspilot' ? (rules && rules.length > 0 ? rules[0] : 0) : 0,
        }))
      );
    }
  }, [visible, node, rules]);

  const fetchGroupDataRule = async () => {
    if (!node?.key) return;

    try {
      const data = await getGroupDataRule({
        params: { group_id: node.key.toString() }
      });
      setDataPermissions(data || []);
    } catch (error) {
      console.error('Failed to fetch group data rule:', error);
      setDataPermissions([]);
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
      render: (_text: unknown, record: AppPermission) => {
        const options = [
          { value: 0, label: t('system.permission.fullPermission') }
        ];
        if (dataPermissions && dataPermissions.length > 0) {
          dataPermissions.forEach(permission => {
            options.push({ value: Number(permission.id), label: permission.name });
          });
        }

        return (
          <Select
            value={record.permission}
            className="w-full"
            options={options}
            disabled={record.app !== 'opspilot'}
            onChange={(value: number) => {
              setAppData(prevData =>
                prevData.map(item =>
                  item.key === record.key ? { ...item, permission: value } : item
                )
              );
            }}
          />
        );
      },
    },
  ];

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
        onCancel();
      }}
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
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default PermissionModal;
