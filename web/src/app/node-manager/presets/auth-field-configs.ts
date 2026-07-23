import {
  createAuthCredentialFieldConfig,
  createAuthTypeFieldConfig,
  createAuthTypeOptions,
} from '@/components/auth-secret-field';

interface TranslateFn {
  (key: string): string;
}

export const createNodeManagerAuthTypeOptions = (t: TranslateFn) =>
  createAuthTypeOptions({
    password: t('node-manager.cloudregion.node.password'),
    privateKey: t('node-manager.cloudregion.node.privateKey'),
  });

interface NodeManagerAuthTypeFieldOptions {
  defaultValue?: unknown;
  placeholder?: string;
  useWidgetProps?: boolean;
}

export const createNodeManagerAuthTypeFieldConfig = (
  t: TranslateFn,
  options: NodeManagerAuthTypeFieldOptions = {},
) =>
  createAuthTypeFieldConfig({
    label: t('node-manager.cloudregion.node.authType'),
    optionLabels: {
      password: t('node-manager.cloudregion.node.password'),
      privateKey: t('node-manager.cloudregion.node.privateKey'),
    },
    defaultValue: options.defaultValue,
    placeholder: options.placeholder,
    useWidgetProps: options.useWidgetProps,
  });

interface NodeManagerAuthCredentialFieldOptions {
  encrypted?: boolean;
  excelLabel?: string;
  placeholder?: string;
}

export const createNodeManagerAuthCredentialFieldConfig = (
  t: TranslateFn,
  options: NodeManagerAuthCredentialFieldOptions = {},
) =>
  createAuthCredentialFieldConfig({
    label: t('node-manager.cloudregion.node.loginPassword'),
    excelLabel: options.excelLabel,
    placeholder: options.placeholder,
    encrypted: options.encrypted,
  });
