import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';

/**
 * 控制器安装表格配置 Hook
 */
export const useTableConfig = (installMethod: string) => {
  const { t } = useTranslation();

  const remoteColumns = [
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
      label: t('node-manager.cloudregion.node.organaziton'),
      type: 'group_select',
      required: true,
      widget_props: {
        placeholder: t('common.selectTip'),
      },
    },
    {
      name: 'port',
      label: t('node-manager.cloudregion.node.loginPort'),
      type: 'inputNumber',
      required: true,
      default_value: 22,
      widget_props: {
        min: 1,
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
      name: 'password',
      label: t('node-manager.cloudregion.node.loginPassword'),
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
      label: t('node-manager.cloudregion.node.organaziton'),
      type: 'group_select',
      required: true,
      widget_props: {
        placeholder: t('common.selectTip'),
      },
    },
  ];

  return useMemo(() => {
    return installMethod === 'remoteInstall' ? remoteColumns : manualColumns;
  }, [installMethod, t]);
};
