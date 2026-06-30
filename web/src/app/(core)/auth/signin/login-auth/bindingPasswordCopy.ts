import type { LoginAuthBindingItem } from "./types";

const bindingFormNameOverrides: Record<string, string> = {
  ad: "AD",
};

function getBindingFormName(binding: LoginAuthBindingItem): string {
  return bindingFormNameOverrides[binding.provider_key] || binding.name;
}

export function getBindingPasswordCopy(binding: LoginAuthBindingItem) {
  const bindingName = getBindingFormName(binding);

  return {
    usernameLabel: `${bindingName} Username`,
    usernamePlaceholder: `Enter your ${bindingName} username`,
    passwordLabel: `${bindingName} Password`,
    passwordPlaceholder: `Enter your ${bindingName} password`,
    submitText: `Sign in with ${bindingName}`,
    loadingText: `Signing in with ${bindingName}...`,
  };
}
