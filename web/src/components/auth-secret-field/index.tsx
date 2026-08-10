'use client';

import React from 'react';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import PrivateKeyUploadField from './privateKeyUpload';

interface AuthSecretFieldProps {
  authType?: string;
  passwordValue?: string;
  passwordPlaceholder?: string;
  passwordDisabled?: boolean;
  passwordClassName?: string;
  fileName?: string;
  privateKeyButtonClassName?: string;
  privateKeyPreviewClassName?: string;
  onPasswordChange?: (value: string) => void;
  onPrivateKeyLoaded: (content: string, fileName: string) => void;
  onPrivateKeyClear: () => void;
}

const AuthSecretField = ({
  authType = 'password',
  passwordValue,
  passwordPlaceholder,
  passwordDisabled,
  passwordClassName,
  fileName,
  privateKeyButtonClassName,
  privateKeyPreviewClassName,
  onPasswordChange,
  onPrivateKeyLoaded,
  onPrivateKeyClear,
}: AuthSecretFieldProps) => {
  if (authType === 'private_key') {
    return (
      <PrivateKeyUploadField
        fileName={fileName}
        buttonClassName={privateKeyButtonClassName}
        previewClassName={privateKeyPreviewClassName}
        onFileLoaded={onPrivateKeyLoaded}
        onClear={onPrivateKeyClear}
      />
    );
  }

  return (
    <EditablePasswordField
      value={passwordValue}
      disabled={passwordDisabled}
      placeholder={passwordPlaceholder}
      className={passwordClassName}
      onChange={onPasswordChange}
    />
  );
};

export default AuthSecretField;
export {
  createAuthTypeOptions,
  createAuthTypeFieldConfig,
  createAuthCredentialFieldConfig,
} from './field-presets';
export {
  noopSecretFieldClear,
  noopSecretFieldLoad,
  createPasswordSecretFieldProps,
} from './presets';
export { default as PrivateKeyUploadField } from './privateKeyUpload';
