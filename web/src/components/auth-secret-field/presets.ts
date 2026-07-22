export const noopSecretFieldClear = () => undefined;

export const noopSecretFieldLoad = () => undefined;

interface PasswordSecretFieldConfig {
  passwordClassName?: string;
  passwordDisabled?: boolean;
  passwordPlaceholder?: string;
  passwordValue?: string;
  onPasswordChange?: (value: string) => void;
}

interface PrivateKeySecretFieldConfig {
  fileName?: string;
  privateKeyButtonClassName?: string;
  privateKeyPreviewClassName?: string;
  onPrivateKeyClear: () => void;
  onPrivateKeyLoaded: (content: string, fileName: string) => void;
}

export const createPasswordSecretFieldProps = ({
  passwordClassName,
  passwordDisabled,
  passwordPlaceholder,
  passwordValue,
  onPasswordChange,
}: PasswordSecretFieldConfig) => ({
  authType: 'password' as const,
  passwordClassName,
  passwordDisabled,
  passwordPlaceholder,
  passwordValue,
  onPasswordChange,
  onPrivateKeyClear: noopSecretFieldClear,
  onPrivateKeyLoaded: noopSecretFieldLoad,
});

export const createPrivateKeySecretFieldProps = ({
  fileName,
  privateKeyButtonClassName,
  privateKeyPreviewClassName,
  onPrivateKeyClear,
  onPrivateKeyLoaded,
}: PrivateKeySecretFieldConfig) => ({
  authType: 'private_key' as const,
  fileName,
  privateKeyButtonClassName,
  privateKeyPreviewClassName,
  onPrivateKeyClear,
  onPrivateKeyLoaded,
});
