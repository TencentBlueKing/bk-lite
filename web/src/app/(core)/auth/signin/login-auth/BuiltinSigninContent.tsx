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

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col space-y-5">
      <div className="space-y-1.5">
        <label
          htmlFor={usernameFieldId}
          className={`font-medium text-(--color-text-1) ${isModalMode ? "text-[13px]" : "text-[13px]"}`}
        >
          {usernameLabel}
        </label>
        <Input
          id={usernameFieldId}
          placeholder={usernamePlaceholder}
          value={username}
          onChange={(event) => onUsernameChange(event.target.value)}
          size="large"
          required
          className={isModalMode ? "h-10 rounded-lg" : "h-11 rounded-lg"}
        />
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor={passwordFieldId}
          className={`font-medium text-(--color-text-1) ${isModalMode ? "text-[13px]" : "text-[13px]"}`}
        >
          {passwordLabel}
        </label>
        <Input.Password
          id={passwordFieldId}
          placeholder={passwordPlaceholder}
          value={password}
          onChange={(event) => onPasswordChange(event.target.value)}
          size="large"
          required
          className={isModalMode ? "h-10 rounded-lg" : "h-11 rounded-lg"}
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className={`w-full rounded-lg bg-[#246BFD] px-4 text-white font-medium transition-all duration-150 ease-in-out hover:bg-[#1F5DE0] ${isModalMode ? "h-11 text-[14px] shadow-[0_12px_28px_rgba(36,107,253,0.24)]" : "h-11 text-[14px] shadow-[0_10px_24px_rgba(36,107,253,0.2)]"} ${isLoading ? "cursor-not-allowed opacity-70" : ""}`}
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
