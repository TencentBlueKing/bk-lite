interface AuthTypeOptionLabels {
  password: string;
  privateKey: string;
}

interface AuthTypeFieldConfig {
  defaultValue?: unknown;
  label: string;
  optionLabels: AuthTypeOptionLabels;
  placeholder?: string;
  required?: boolean;
  useWidgetProps?: boolean;
}

interface AuthCredentialFieldConfig {
  encrypted?: boolean;
  excelLabel?: string;
  label: string;
  placeholder?: string;
  required?: boolean;
}

export const createAuthTypeOptions = ({
  password,
  privateKey,
}: AuthTypeOptionLabels) => [
  { label: password, value: 'password' },
  { label: privateKey, value: 'private_key' },
];

export const createAuthTypeFieldConfig = ({
  defaultValue,
  label,
  optionLabels,
  placeholder,
  required = true,
  useWidgetProps = false,
}: AuthTypeFieldConfig) => {
  const options = createAuthTypeOptions(optionLabels);

  return {
    name: 'auth_type',
    label,
    type: 'select' as const,
    required,
    ...(defaultValue !== undefined ? { default_value: defaultValue } : {}),
    ...(useWidgetProps
      ? {
        widget_props: {
          ...(placeholder ? { placeholder } : {}),
          options,
        },
      }
      : {
        ...(placeholder ? { widget_props: { placeholder } } : {}),
        options,
      }),
  };
};

export const createAuthCredentialFieldConfig = ({
  encrypted,
  excelLabel,
  label,
  placeholder,
  required = true,
}: AuthCredentialFieldConfig) => ({
  name: 'password',
  label,
  ...(excelLabel ? { excel_label: excelLabel } : {}),
  type: 'auth_input' as const,
  required,
  ...(placeholder ? { widget_props: { placeholder } } : {}),
  ...(encrypted !== undefined ? { encrypted } : {}),
});
