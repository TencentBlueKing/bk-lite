"use client";

import { Input } from "antd";
import { LoadingOutlined } from "@ant-design/icons";
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
  const pageInputClassName = "h-10 rounded-md";
  const pageButtonClassName = "h-10 rounded-md text-sm";

  return (
    <form
      onSubmit={onSubmit}
      className={`flex w-full flex-col space-y-4 ${isModalMode ? "" : "mx-auto max-w-[420px]"}`}
    >
      <div>
        <label
          htmlFor={usernameFieldId}
          className="mb-1.5 block text-[13px] font-medium text-(--color-text-1)"
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
            autoComplete="username"
          />
        ) : (
          <Input id={usernameFieldId} placeholder={usernamePlaceholder} value={username} onChange={(event) => onUsernameChange(event.target.value)} size="large" required autoComplete="username" className={pageInputClassName} />
        )}
      </div>

      <div>
        <label
          htmlFor={passwordFieldId}
          className="mb-1.5 block text-[13px] font-medium text-(--color-text-1)"
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
            autoComplete="current-password"
          />
        ) : (
          <Input.Password id={passwordFieldId} placeholder={passwordPlaceholder} value={password} onChange={(event) => onPasswordChange(event.target.value)} size="large" required autoComplete="current-password" className={pageInputClassName} />
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className={`w-full bg-(--color-primary) px-4 font-medium text-white transition-colors duration-150 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-primary) ${isModalMode ? "h-10 rounded-md text-[14px]" : pageButtonClassName} ${isLoading ? "cursor-not-allowed opacity-70" : ""}`}
      >
        {isLoading ? (
          <span aria-live="polite" className="flex items-center justify-center">
            <LoadingOutlined spin className="-ml-1 mr-3 text-xl text-white" />
            {loadingText}
          </span>
        ) : (
          submitText
        )}
      </button>
    </form>
  );
}
