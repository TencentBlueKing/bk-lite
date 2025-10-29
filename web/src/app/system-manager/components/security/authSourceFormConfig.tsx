import React from 'react';
import { CopyOutlined } from '@ant-design/icons';
import { FormInstance, TimePicker } from 'antd';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import dayjs from 'dayjs';

interface FormConfigParams {
  t: (key: string) => string;
  roleTreeData: TreeDataNode[];
  selectedRoles: number[];
  setSelectedRoles: (roles: number[]) => void;
  dynamicForm: FormInstance;
  copyToClipboard: (text: string) => void;
  isBuiltIn?: boolean;
}

export const getNewAuthSourceFormFields = ({
  t,
  roleTreeData,
  selectedRoles,
  setSelectedRoles,
  dynamicForm,
  isBuiltIn = false
}: FormConfigParams) => [
  {
    name: 'name',
    type: 'input',
    label: t('system.security.authSourceName'),
    placeholder: `${t('common.inputMsg')}${t('system.security.authSourceName')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.authSourceName')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'source_type',
    type: 'select',
    label: t('system.security.authSourceType'),
    placeholder: `${t('common.select')}${t('system.security.authSourceType')}`,
    options: [
      { value: 'bk_lite', label: 'BK-Lite认证源' },
      { value: 'bk_login', label: '蓝鲸认证源' }
    ],
    rules: [{ required: true, message: `${t('common.select')}${t('system.security.authSourceType')}` }],
    initialValue: 'bk_lite',
    disabled: isBuiltIn
  },
  {
    name: 'namespace',
    type: 'input',
    label: t('system.security.namespace'),
    placeholder: `${t('common.inputMsg')}${t('system.security.namespace')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.namespace')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'root_group',
    type: 'input',
    label: t('system.security.rootGroup'),
    placeholder: `${t('common.inputMsg')}${t('system.security.rootGroup')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.rootGroup')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'domain',
    type: 'input',
    label: t('system.security.domain'),
    placeholder: `${t('common.inputMsg')}${t('system.security.domain')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.domain')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'default_roles',
    type: 'custom',
    label: t('system.security.defaultRoles'),
    component: (
      <RoleTransfer
        treeData={roleTreeData}
        selectedKeys={selectedRoles}
        disabled={isBuiltIn}
        onChange={newKeys => {
          setSelectedRoles(newKeys);
          dynamicForm.setFieldsValue({ default_roles: newKeys });
        }}
      />
    ),
    rules: [{ required: true, message: `${t('common.selectMsg')}${t('system.security.defaultRoles')}` }],
  },
  {
    name: 'sync',
    type: 'switch',
    label: t('system.security.syncEnabled'),
    size: 'small',
    initialValue: false
  },
  {
    name: 'sync_time',
    type: 'custom',
    label: t('system.security.syncTime'),
    component: (
      <div className="flex items-center flex-nowrap whitespace-nowrap text-gray-500">
        <span className="mr-2 flex-shrink-0">{t('system.security.everyday')}</span>
        <TimePicker
          format="HH:mm"
          placeholder={t('system.security.selectTime')}
          value={dynamicForm.getFieldValue('sync_time') ? dayjs(dynamicForm.getFieldValue('sync_time'), 'HH:mm') : undefined}
          onChange={(time) => {
            const timeString = time ? time.format('HH:mm') : '';
            console.log('Selected sync time:', timeString);
            dynamicForm.setFieldsValue({ sync_time: timeString });
          }}
          className="mx-2 min-w-[100px]"
        />
        <span className="ml-2 flex-shrink-0">{t('system.security.syncOnce')}</span>
      </div>
    )
  },
  {
    name: 'enabled',
    type: 'switch',
    label: t('system.security.enabled'),
    size: 'small',
    initialValue: true,
    disabled: isBuiltIn
  }
];

export const getBluekingFormFields = ({
  t,
  roleTreeData,
  selectedRoles,
  setSelectedRoles,
  dynamicForm,
  isBuiltIn = false
}: FormConfigParams) => [
  {
    name: 'name',
    type: 'input',
    label: t('system.security.authSourceName'),
    placeholder: `${t('common.inputMsg')}${t('system.security.authSourceName')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.authSourceName')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'source_type',
    type: 'select',
    label: t('system.security.authSourceType'),
    placeholder: `${t('common.select')}${t('system.security.authSourceType')}`,
    options: [
      { value: 'bk_lite', label: 'BK-Lite认证源' },
      { value: 'bk_login', label: '蓝鲸认证源' }
    ],
    rules: [{ required: true, message: `${t('common.select')}${t('system.security.authSourceType')}` }],
    initialValue: 'bk_login',
    disabled: isBuiltIn
  },
  {
    name: 'root_group',
    type: 'input',
    label: t('system.security.rootGroup'),
    placeholder: `${t('common.inputMsg')}${t('system.security.rootGroup')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.rootGroup')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'app_id',
    type: 'input',
    label: t('system.security.appId'),
    placeholder: `${t('common.inputMsg')}${t('system.security.appId')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.appId')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'app_token',
    type: 'editablePwd',
    label: t('system.security.appSecret'),
    placeholder: `${t('common.inputMsg')}${t('system.security.appSecret')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.appSecret')}` }],
    disabled: isBuiltIn
  },
  {
    name: 'bk_url',
    type: 'input',
    label: '认证URL',
    placeholder: '请输入认证URL',
    rules: [{ required: true, message: '请输入认证URL' }],
    disabled: isBuiltIn
  },
  {
    name: 'default_roles',
    type: 'custom',
    label: t('system.security.defaultRoles'),
    component: (
      <RoleTransfer
        treeData={roleTreeData}
        selectedKeys={selectedRoles}
        disabled={isBuiltIn}
        onChange={newKeys => {
          setSelectedRoles(newKeys);
          dynamicForm.setFieldsValue({ default_roles: newKeys });
        }}
      />
    ),
    rules: [{ required: true, message: `${t('common.selectMsg')}${t('system.security.defaultRoles')}` }],
  },
  {
    name: 'enabled',
    type: 'switch',
    label: t('system.security.enabled'),
    size: 'small',
    initialValue: true,
    disabled: isBuiltIn
  }
];

export const getWeChatFormFields = ({
  t,
  dynamicForm,
  copyToClipboard
}: FormConfigParams) => [
  {
    name: 'name',
    type: 'input',
    label: t('system.security.loginMethodName'),
    placeholder: `${t('common.inputMsg')}${t('system.security.loginMethodName')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.loginMethodName')}` }]
  },
  {
    name: 'app_id',
    type: 'input',
    label: t('system.security.appId'),
    placeholder: `${t('common.inputMsg')}${t('system.security.appId')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.appId')}` }]
  },
  {
    name: 'app_secret',
    type: 'editablePwd',
    label: t('system.security.appSecret'),
    placeholder: `${t('common.inputMsg')}${t('system.security.appSecret')}`,
    rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.security.appSecret')}` }]
  },
  {
    name: 'redirect_uri',
    type: 'input',
    label: t('system.security.redirectUri'),
    placeholder: `${t('common.inputMsg')}${t('system.security.redirectUri')}`,
    suffix: <CopyOutlined onClick={() => copyToClipboard(dynamicForm.getFieldValue('redirect_uri'))} />
  },
  {
    name: 'enabled',
    type: 'switch',
    label: t('system.security.enabled'),
    initialValue: true,
    size: 'small'
  }
];