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
  activeBindingName,
  errorMessage,
  onRetryBindings,
  onContinueThirdParty,
}: LoginAuthBindingContentProps) {
  const isModalMode = mode === "modal";

  if (bindingLoadState === "loading-bindings") {
    return (
      <div className="flex min-h-[216px] items-center justify-center rounded-2xl border border-[#E9EDF5] bg-white/72 px-6 py-6 shadow-[0_10px_26px_rgba(15,23,42,0.04)]">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#F4F7FB] text-[18px] text-(--color-text-3)">
          <LoadingOutlined />
        </div>
      </div>
    );
  }

  if (bindingLoadState === "bindings-error") {
    return (
      <div className="rounded-[24px] border border-[#E9EDF5] bg-white/88 px-6 py-7 text-center shadow-[0_10px_26px_rgba(15,23,42,0.04)]">
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
          className={`mt-5 inline-flex items-center justify-center rounded-xl bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
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
      <div className="rounded-[24px] border border-[#E9EDF5] bg-white/88 px-6 py-8 text-center shadow-[0_10px_26px_rgba(15,23,42,0.04)]">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#F4F8FF] text-[#246BFD]">
          <LoadingOutlined className={`text-[24px] ${viewState === "syncing-session" ? "" : "animate-spin"}`} />
        </div>
        <div className={`mt-5 font-semibold text-(--color-text-1) ${isModalMode ? "text-[15px]" : "text-[18px]"}`}>
          {getWaitingTitle(viewState)}
        </div>
        <p className={`mt-2 text-(--color-text-3) ${isModalMode ? "text-[12px] leading-5" : "text-sm leading-6"}`}>
          {viewState === "syncing-session"
            ? "Finalizing your BK-Lite session."
            : `Continue with ${activeBindingName || selectedBinding.name} in the newly opened tab.`}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-[24px] border border-[#E9EDF5] bg-white/88 px-6 py-7 text-center shadow-[0_10px_26px_rgba(15,23,42,0.04)]">
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[20px] bg-[#F4F7FB]">
        {selectedBinding.icon ? (
          <Icon type={selectedBinding.icon} className="h-8! w-8! text-[#246BFD]" />
        ) : (
          <div className="text-[28px] leading-none text-[#246BFD]">#</div>
        )}
      </div>
      <div className={`mt-5 font-semibold text-(--color-text-1) ${isModalMode ? "text-[15px]" : "text-[18px]"}`}>
        {selectedBinding.name}
      </div>
      <p className={`mt-2 text-(--color-text-3) ${isModalMode ? "text-[12px] leading-5" : "text-sm leading-6"}`}>
        {selectedBinding.description || "Continue with this login method to authenticate your account."}
      </p>
      <button
        type="button"
        onClick={onContinueThirdParty}
        className={`mt-5 inline-flex items-center justify-center rounded-xl bg-[#246BFD] px-4 text-white transition-colors hover:bg-[#1F5DE0] ${isModalMode ? "h-10 text-[13px]" : "h-11 text-sm font-medium"}`}
      >
        Continue sign-in
      </button>
    </div>
  );
}
