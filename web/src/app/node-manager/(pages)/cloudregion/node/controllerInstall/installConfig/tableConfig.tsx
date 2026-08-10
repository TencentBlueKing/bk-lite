import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';

/**
 * 控制器安装表格配置 Hook
 */
export const useTableConfig = (installMethod: string, os: string) => {
  const { t } = useTranslation();

  const identityColumns = [
    {
      name: 'ip',
      label: t('node-manager.cloudregion.node.ipAdrress'),
      type: 'input',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
      rules: [
        {
          type: 'pattern',
          pattern:
            '^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
          message: t('node-manager.cloudregion.deploy.ipFormatError'),
          excel_formula:
            'AND(LEN({{CELL}})>=7,LEN({{CELL}})<=15,ISNUMBER(FIND(".",{{CELL}})))',
        },
      ],
    },
    {
      name: 'node_name',
      label: t('node-manager.cloudregion.node.nodeName'),
      type: 'input',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'organizations',
      label: t('node-manager.cloudregion.node.organization'),
      type: 'group_select',
      required: true,
      widget_props: {
        placeholder: t('common.selectTip'),
      },
    },
  ];

  const linuxRemoteColumns = [
    ...identityColumns,
    {
      name: 'port',
      label: t('node-manager.cloudregion.node.loginPort'),
      type: 'inputNumber',
      required: true,
      default_value: 22,
      widget_props: {
        min: 1,
        max: 65535,
        precision: 0,
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'username',
      label: t('node-manager.cloudregion.node.loginAccount'),
      type: 'input',
      required: true,
      default_value: 'root',
      widget_props: {
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'auth_type',
      label: t('node-manager.cloudregion.node.authType'),
      type: 'select',
      required: true,
      default_value: 'password',
      widget_props: {
        placeholder: t('common.selectTip'),
        options: [
          {
            label: t('node-manager.cloudregion.node.password'),
            value: 'password',
          },
          {
            label: t('node-manager.cloudregion.node.privateKey'),
            value: 'private_key',
          },
        ],
      },
    },
    {
      name: 'password',
      label: t('node-manager.cloudregion.node.loginPassword'),
      excel_label: t('node-manager.cloudregion.node.excelLoginPassword'),
      type: 'auth_input',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
      encrypted: true,
    },
  ];

  const windowsRemoteColumns = [
    ...identityColumns,
    {
      name: 'port',
      label: t('node-manager.cloudregion.node.loginPort'),
      type: 'inputNumber',
      required: true,
      default_value: 5986,
      widget_props: {
        min: 1,
        max: 65535,
        precision: 0,
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'username',
      label: t('node-manager.cloudregion.node.loginAccount'),
      type: 'input',
      required: true,
      default_value: 'Administrator',
      widget_props: {
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'password',
      label: t('node-manager.cloudregion.node.windowsLoginPassword'),
      excel_label: t('node-manager.cloudregion.node.excelLoginPassword'),
      type: 'password',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
      encrypted: true,
    },
  ];

  const manualColumns = [
    {
      name: 'ip',
      label: t('node-manager.cloudregion.node.ipAdrress'),
      type: 'input',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
      rules: [
        {
          type: 'pattern',
          pattern:
            '^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
          message: t('node-manager.cloudregion.deploy.ipFormatError'),
          excel_formula:
            'AND(LEN({{CELL}})>=7,LEN({{CELL}})<=15,ISNUMBER(FIND(".",{{CELL}})))',
        },
      ],
    },
    {
      name: 'node_name',
      label: t('node-manager.cloudregion.node.nodeName'),
      type: 'input',
      required: true,
      widget_props: {
        placeholder: t('common.inputTip'),
      },
    },
    {
      name: 'organizations',
      label: t('node-manager.cloudregion.node.organization'),
      type: 'group_select',
      required: true,
      widget_props: {
        placeholder: t('common.selectTip'),
      },
    },
  ];

  return useMemo(() => {
    if (installMethod !== 'remoteInstall') {
      return manualColumns;
    }
    return os === 'windows' ? windowsRemoteColumns : linuxRemoteColumns;
  }, [installMethod, os, t]);
};
