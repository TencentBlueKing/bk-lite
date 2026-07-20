"use client";

import { LoadingOutlined, ReloadOutlined } from "@ant-design/icons";
import Icon from "@/components/icon";
import { useTranslation } from "@/utils/i18n";
import type {
  LoginAuthBindingItem,
  LoginAuthBindingsLoadState,
  LoginAuthValidationViewState,
} from "./types";

interface LoginAuthBindingContentProps {
  mode: "page" | "modal";
  bindingLoadState: LoginAuthBindingsLoadState;
  selectedBinding: LoginAuthBindingItem | null;
  viewState: LoginAuthValidationViewState;
  activeBindingName: string;
  errorMessage: string;
  onRetryBindings: () => void;
  onContinueThirdParty: () => void;
}

function getWaitingTitle(
  viewState: LoginAuthValidationViewState,
  t: (id: string) => string,
) {
  if (viewState === "syncing-session") {
    return t('signin.loginAuth.bindingContent.completingSignIn');
  }

  if (viewState === "starting") {
    return t('signin.loginAuth.bindingContent.startingAuthentication');
  }

  return t('signin.loginAuth.bindingContent.waitingForAuthentication');
}

export default function LoginAuthBindingContent({
  mode,
  bindingLoadState,
  selectedBinding,
  viewState,
  errorMessage,
  onRetryBindings,
  onContinueThirdParty,
}: LoginAuthBindingContentProps) {
  const { t } = useTranslation();
  const isModalMode = mode === "modal";
  const helperMessage = t('signin.loginAuth.bindingContent.helperMessage');
  const pageBindingCardClassName =
    "rounded-md border border-(--color-border) bg-(--color-bg) px-[14px] py-[12px]";
  const modalBindingCardClassName = pageBindingCardClassName;
  const bindingCardClassName = isModalMode ? modalBindingCardClassName : pageBindingCardClassName;
  const pageHelperCardClassName =
    "mt-3 rounded-md bg-(--color-fill-1) px-3 py-[10px] text-[12px] leading-[1.6] text-(--color-text-2)";
  const modalHelperCardClassName = pageHelperCardClassName;
  const helperCardClassName = isModalMode ? modalHelperCardClassName : pageHelperCardClassName;
  const pageBindingIconClassName =
    "flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-md bg-(--color-primary-bg-active)";
  const modalBindingIconClassName = pageBindingIconClassName;
  const bindingIconClassName = isModalMode ? modalBindingIconClassName : pageBindingIconClassName;
  const bindingIconSizeClassName = isModalMode ? "h-5! w-5!" : "h-6! w-6!";
  const bindingFallbackIconClassName = isModalMode ? "text-[18px]" : "text-[20px]";

  if (bindingLoadState === "loading-bindings") {
    return (
      <div className="flex min-h-[196px] items-center justify-center px-4 py-6">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#F4F7FB] text-[18px] text-(--color-text-3)">
          <LoadingOutlined />
        </div>
      </div>
    );
  }

  if (bindingLoadState === "bindings-error") {
    return (
      <div className="px-1 py-2 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#FFF4E8] text-[#D46B08]">
          <ReloadOutlined />
        </div>
        <div className={`mt-4 font-semibold text-(--color-text-1) ${isModalMode ? "text-[15px]" : "text-[17px]"}`}>
          {t('signin.loginAuth.bindingContent.loadErrorTitle')}
        </div>
        <p className={`mt-2 text-(--color-text-3) ${isModalMode ? "text-[12px] leading-5" : "text-sm leading-6"}`}>
          {errorMessage || t('signin.loginAuth.bindingContent.loadErrorDescription')}
        </p>
        <button
          type="button"
          onClick={onRetryBindings}
          className={`mt-5 inline-flex items-center justify-center rounded-lg bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
        >
          {t('signin.loginAuth.bindingContent.retry')}
        </button>
      </div>
    );
  }

  if (!selectedBinding) {
    return null;
  }

  if (viewState === "starting" || viewState === "waiting" || viewState === "syncing-session") {
    return (
      <div className="px-1 py-1">
        <div className={bindingCardClassName}>
          <div className="flex items-center gap-[10px]">
            <div className={bindingIconClassName}>
              {selectedBinding.icon ? (
                <Icon type={selectedBinding.icon} className={`${bindingIconSizeClassName} text-[#246BFD]`} />
              ) : (
                <div className={`${bindingFallbackIconClassName} leading-none text-[#246BFD]`}>#</div>
              )}
            </div>
            <div className="min-w-0">
              <div className={`font-semibold text-[#1E4FD6] ${isModalMode ? "text-[13px] leading-[1.35]" : "text-[14px] leading-[1.4]"}`}>
                {t('signin.loginAuth.bindingContent.bindingTitle', undefined, { bindingName: selectedBinding.name })}
              </div>
              <div className="mt-[2px] text-[12px] leading-[1.45] text-[#7A8A9D]">
                {getWaitingTitle(viewState, t)}
              </div>
            </div>
          </div>
        </div>
        <button
          type="button"
          disabled
          className={`mt-5 inline-flex w-full items-center justify-center gap-2 rounded-[8px] bg-[#246BFD] px-4 text-white opacity-90 ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
        >
          <LoadingOutlined className={viewState === "syncing-session" ? "" : "animate-spin"} />
          <span>{t('signin.loginAuth.bindingContent.waiting')}</span>
        </button>
        <p className={helperCardClassName}>
          {helperMessage}
        </p>
      </div>
    );
  }

  return (
    <div className="px-1 py-1">
      <div className={bindingCardClassName}>
        <div className="flex items-center gap-[10px]">
          <div className={bindingIconClassName}>
            {selectedBinding.icon ? (
              <Icon type={selectedBinding.icon} className={`${bindingIconSizeClassName} text-[#246BFD]`} />
            ) : (
              <div className={`${bindingFallbackIconClassName} leading-none text-[#246BFD]`}>#</div>
            )}
          </div>
          <div className="min-w-0">
            <div className={`font-semibold text-[var(--color-text-1)] ${isModalMode ? "text-[13px] leading-[1.35]" : "text-[14px] leading-[1.4]"}`}>
              {t('signin.loginAuth.bindingContent.bindingTitle', undefined, { bindingName: selectedBinding.name })}
            </div>
            <div className="mt-[2px] text-[12px] leading-[1.45] text-[#7A8A9D]">
              {t('signin.loginAuth.bindingContent.bindingDescription', undefined, { bindingName: selectedBinding.name })}
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={onContinueThirdParty}
        className={`mt-5 inline-flex w-full items-center justify-center rounded-[8px] bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
      >
        {t('signin.loginAuth.bindingContent.continueSignIn')}
      </button>
      <p className={helperCardClassName}>
        {helperMessage}
      </p>
    </div>
  );
}
