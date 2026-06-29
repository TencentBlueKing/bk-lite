"use client";

import { LoadingOutlined, ReloadOutlined } from "@ant-design/icons";
import Icon from "@/components/icon";
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

function getWaitingTitle(viewState: LoginAuthValidationViewState) {
  if (viewState === "syncing-session") {
    return "Completing sign-in";
  }

  if (viewState === "starting") {
    return "Starting authentication";
  }

  return "Waiting for authentication";
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
  const isModalMode = mode === "modal";
  const helperMessage = "点击后将在新窗口中完成验证。若未跳转，可检查浏览器是否拦截弹窗。";

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
          Unable to load login methods
        </div>
        <p className={`mt-2 text-(--color-text-3) ${isModalMode ? "text-[12px] leading-5" : "text-sm leading-6"}`}>
          {errorMessage || "Please retry to load the available sign-in options."}
        </p>
        <button
          type="button"
          onClick={onRetryBindings}
          className={`mt-5 inline-flex items-center justify-center rounded-lg bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
        >
          Retry
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
        <div className="rounded-[8px] border border-[#DBE5F2] bg-[linear-gradient(180deg,#FBFCFE_0%,#F4F8FC_100%)] px-[14px] py-[12px]">
          <div className="flex items-center gap-[10px]">
            <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[8px] bg-[#E8F0FF]">
              {selectedBinding.icon ? (
                <Icon type={selectedBinding.icon} className="h-5! w-5! text-[#246BFD]" />
              ) : (
                <div className="text-[18px] leading-none text-[#246BFD]">#</div>
              )}
            </div>
            <div className="min-w-0">
              <div className={`font-semibold text-[#1E4FD6] ${isModalMode ? "text-[13px] leading-[1.35]" : "text-[14px] leading-[1.4]"}`}>
                {selectedBinding.name}登录
              </div>
              <div className="mt-[2px] text-[12px] leading-[1.45] text-[#7A8A9D]">
                {getWaitingTitle(viewState)}
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
          <span>Waiting...</span>
        </button>
        <p className="mt-3 rounded-[8px] border border-[#D7E0EA] bg-[#F8FAFC] px-3 py-[10px] text-[12px] leading-[1.6] text-[#708094]">
          {helperMessage}
        </p>
      </div>
    );
  }

  return (
    <div className="px-1 py-1">
      <div className="rounded-[8px] border border-[#DBE5F2] bg-[linear-gradient(180deg,#FBFCFE_0%,#F4F8FC_100%)] px-[14px] py-[12px]">
        <div className="flex items-center gap-[10px]">
          <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[8px] bg-[#E8F0FF]">
            {selectedBinding.icon ? (
              <Icon type={selectedBinding.icon} className="h-5! w-5! text-[#246BFD]" />
            ) : (
              <div className="text-[18px] leading-none text-[#246BFD]">#</div>
            )}
          </div>
          <div className="min-w-0">
            <div className={`font-semibold text-[var(--color-text-1)] ${isModalMode ? "text-[13px] leading-[1.35]" : "text-[14px] leading-[1.4]"}`}>
              {selectedBinding.name}登录
            </div>
            <div className="mt-[2px] text-[12px] leading-[1.45] text-[#7A8A9D]">
              使用{selectedBinding.name}账号完成登录
            </div>
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={onContinueThirdParty}
        className={`mt-5 inline-flex w-full items-center justify-center rounded-[8px] bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
      >
        Click to continue sign in
      </button>
      <p className="mt-3 rounded-[8px] border border-[#D7E0EA] bg-[#F8FAFC] px-3 py-[10px] text-[12px] leading-[1.6] text-[#708094]">
        {helperMessage}
      </p>
    </div>
  );
}
