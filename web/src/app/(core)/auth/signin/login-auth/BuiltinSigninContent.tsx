"use client";

import { Input } from "antd";
import type { FormEvent } from "react";

interface BuiltinSigninContentProps {
  mode: "page" | "modal";
  username: string;
  password: string;
  isLoading: boolean;
  usernameLabel: string;
  usernamePlaceholder: string;
  passwordLabel: string;
  passwordPlaceholder: string;
  submitText: string;
  loadingText: string;
  fieldIdPrefix?: string;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export default function BuiltinSigninContent({
  mode,
  username,
  password,
  isLoading,
  usernameLabel,
  usernamePlaceholder,
  passwordLabel,
  passwordPlaceholder,
  submitText,
  loadingText,
  fieldIdPrefix = "builtin",
  onUsernameChange,
  onPasswordChange,
  onSubmit,
}: BuiltinSigninContentProps) {
  const isModalMode = mode === "modal";
  const usernameFieldId = `${fieldIdPrefix}-username`;
  const passwordFieldId = `${fieldIdPrefix}-password`;
  const pageInputShellClassName =
    "flex h-12 items-center rounded-lg border-[1.5px] border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.16)_0%,rgba(255,255,255,0.07)_100%)] px-3 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.32)] backdrop-blur-[16px]";
  const pageInputClassName =
    "h-full !bg-transparent !px-0 !text-[#334a72] !shadow-none placeholder:!text-[#b9c5da]";
  const pagePasswordClassName =
    "h-full !bg-transparent !px-0 !text-[#334a72] !shadow-none [&_.ant-input]:!bg-transparent [&_.ant-input]:!px-0 [&_.ant-input]:!text-[#334a72] [&_.ant-input]:!shadow-none [&_.ant-input]:placeholder:!text-[#b9c5da] [&_.ant-input-password-icon]:!text-[#8fa0bf]";
  const pageButtonClassName =
    "h-12 rounded-lg text-[15px] shadow-[0_18px_36px_rgba(36,107,253,0.28)]";

  return (
    <form
      onSubmit={onSubmit}
      className={`flex w-full flex-col space-y-5 ${isModalMode ? "" : "mx-auto max-w-[420px]"}`}
    >
      <div>
        <label
          htmlFor={usernameFieldId}
          className={`block font-medium ${isModalMode ? "mb-1.5 text-(--color-text-1) text-[13px]" : "mb-3 text-[13px] text-[#31456a]"}`}
        >
          {usernameLabel}
        </label>
        {isModalMode ? (
          <Input
            id={usernameFieldId}
            placeholder={usernamePlaceholder}
            value={username}
            onChange={(event) => onUsernameChange(event.target.value)}
            size="large"
            required
            className="h-10 rounded-lg"
          />
        ) : (
          <div className={pageInputShellClassName}>
            <Input
              id={usernameFieldId}
              placeholder={usernamePlaceholder}
              value={username}
              onChange={(event) => onUsernameChange(event.target.value)}
              size="large"
              required
              variant="borderless"
              className={pageInputClassName}
            />
          </div>
        )}
      </div>

      <div>
        <label
          htmlFor={passwordFieldId}
          className={`block font-medium ${isModalMode ? "mb-1.5 text-(--color-text-1) text-[13px]" : "mb-3 text-[13px] text-[#31456a]"}`}
        >
          {passwordLabel}
        </label>
        {isModalMode ? (
          <Input.Password
            id={passwordFieldId}
            placeholder={passwordPlaceholder}
            value={password}
            onChange={(event) => onPasswordChange(event.target.value)}
            size="large"
            required
            className="h-10 rounded-lg"
          />
        ) : (
          <div className={pageInputShellClassName}>
            <Input.Password
              id={passwordFieldId}
              placeholder={passwordPlaceholder}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              size="large"
              required
              variant="borderless"
              className={pagePasswordClassName}
            />
          </div>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className={`w-full bg-[#246BFD] px-4 text-white font-medium transition-all duration-150 ease-in-out hover:from-[#4378f0] hover:to-[#5a95fb] ${isModalMode ? "h-11 rounded-lg text-[14px] shadow-[0_12px_28px_rgba(36,107,253,0.24)]" : pageButtonClassName} ${isLoading ? "cursor-not-allowed opacity-70" : ""}`}
      >
        {isLoading ? (
          <span className="flex items-center justify-center">
            <svg className="-ml-1 mr-3 h-5 w-5 animate-spin text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 718-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            {loadingText}
          </span>
        ) : (
          submitText
        )}
      </button>
    </form>
  );
}
