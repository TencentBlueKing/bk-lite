import type { LoginAuthBindingItem } from "./types";

const bindingFormNameOverrides: Record<string, string> = {
  ad: "AD",
};

function getBindingFormName(binding: LoginAuthBindingItem): string {
  return bindingFormNameOverrides[binding.provider_key] || binding.name;
}

export function getBindingPasswordCopy(
  binding: LoginAuthBindingItem,
  t: (id: string, defaultMessage?: string, values?: Record<string, string>) => string,
) {
  const bindingName = getBindingFormName(binding);
  const values = { bindingName };

  return {
    usernameLabel: t('signin.loginAuth.bindingPassword.usernameLabel', undefined, values),
    usernamePlaceholder: t('signin.loginAuth.bindingPassword.usernamePlaceholder', undefined, values),
    passwordLabel: t('signin.loginAuth.bindingPassword.passwordLabel', undefined, values),
    passwordPlaceholder: t('signin.loginAuth.bindingPassword.passwordPlaceholder', undefined, values),
    submitText: t('signin.loginAuth.bindingPassword.submitText', undefined, values),
    loadingText: t('signin.loginAuth.bindingPassword.loadingText', undefined, values),
  };
}
