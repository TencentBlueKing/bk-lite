"use client";

import { useEffect, useRef, useState } from "react";
import { toSafeRelativeCallbackUrl } from "@/utils/authRedirect";
import {
  resolveBindingsLoadState,
  resolveInitialBindingId,
  resolveSelectedBinding,
} from "./orderedBindingState";
import type {
  LoginAuthBindingItem,
  LoginAuthBindingsLoadState,
  LoginAuthLoginResult,
  LoginAuthStatusResponseData,
  LoginAuthValidationViewState,
  StartLoginAuthResponseData,
} from "./types";

interface UseLoginAuthValidationOptions {
  enabled: boolean;
  callbackUrl: string;
  onOtpRequired: (loginResult: LoginAuthLoginResult) => void;
  onSessionSync: (loginResult: LoginAuthLoginResult) => Promise<boolean>;
}

interface ActiveRequestMeta {
  authRequestId: string;
  pollToken: string;
  expiresAt: string;
}

function isOtpChallengeResult(loginResult?: LoginAuthLoginResult): boolean {
  return Boolean(loginResult?.require_otp && loginResult?.challenge_id);
}

function isTokenReadyResult(loginResult?: LoginAuthLoginResult): boolean {
  return Boolean(loginResult?.token && (loginResult?.id || loginResult?.username));
}

export function useLoginAuthValidation({
  enabled,
  callbackUrl,
  onOtpRequired,
  onSessionSync,
}: UseLoginAuthValidationOptions) {
  const [bindings, setBindings] = useState<LoginAuthBindingItem[]>([]);
  const [bindingsLoadState, setBindingsLoadState] = useState<LoginAuthBindingsLoadState>("loading-bindings");
  const [isLoadingBindings, setIsLoadingBindings] = useState(false);
  const [viewState, setViewState] = useState<LoginAuthValidationViewState>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [activeBindingId, setActiveBindingId] = useState<number | null>(null);
  const [activeBindingName, setActiveBindingName] = useState("");
  const [activeRequest, setActiveRequest] = useState<ActiveRequestMeta | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);
  const selectedBinding = resolveSelectedBinding(bindings, selectedBindingId);

  const stopPolling = () => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    pollingInFlightRef.current = false;
  };

  const resetFlow = () => {
    stopPolling();
    setActiveRequest(null);
    setActiveBindingName("");
    setErrorMessage("");
    setViewState("idle");
  };

  const resetSelectionState = (nextState: Extract<LoginAuthValidationViewState, "failed" | "cancelled" | "expired">, nextErrorMessage: string) => {
    stopPolling();
    setActiveRequest(null);
    setActiveBindingName("");
    setViewState(nextState);
    setErrorMessage(nextErrorMessage);
  };

  const fetchBindings = async () => {
    setIsLoadingBindings(true);
    setBindingsLoadState("loading-bindings");
    setErrorMessage("");

    try {
      const response = await fetch("/api/proxy/core/api/get_login_auth_bindings/", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
      });
      const responseData = await response.json();

      if (!response.ok || !responseData?.result || !Array.isArray(responseData?.data)) {
        throw new Error(responseData?.message || "Failed to load login auth bindings");
      }

      const nextBindings = responseData.data as LoginAuthBindingItem[];
      setBindings(nextBindings);
      setBindingsLoadState(resolveBindingsLoadState(nextBindings, false));
      setSelectedBindingId((current) => {
        if (current && nextBindings.some((binding) => binding.id === current)) {
          return current;
        }

        return resolveInitialBindingId(nextBindings);
      });
    } catch (error) {
      console.error("Failed to fetch login auth bindings:", error);
      setBindings([]);
      setBindingsLoadState("bindings-error");
      setErrorMessage("Failed to load login methods. Please refresh and try again.");
      setSelectedBindingId(null);
    } finally {
      setIsLoadingBindings(false);
    }
  };

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const loadBindings = async () => {
      await fetchBindings();
    };

    void loadBindings();
  }, [enabled]);

  useEffect(() => () => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
    }
  }, []);

  const resolveTerminalStatus = async (statusData: LoginAuthStatusResponseData) => {
    const status = statusData.status;

    if (status === "expired" || status === "failed" || status === "cancelled") {
      resetSelectionState(
        status,
        statusData.error_message
          || (status === "expired"
            ? "Authentication timed out. Please try again."
            : status === "cancelled"
              ? "Authentication was cancelled. Please try again."
              : "Authentication failed. Please try again."),
      );
      return;
    }

    if (status !== "success") {
      return;
    }

    setViewState("syncing-session");

    const loginResult = statusData.login_result;
    if (isOtpChallengeResult(loginResult)) {
      onOtpRequired(loginResult as LoginAuthLoginResult);
      return;
    }

    if (!isTokenReadyResult(loginResult)) {
      resetSelectionState("failed", "Authentication succeeded, but the returned login payload is incomplete.");
      return;
    }

    const synced = await onSessionSync(loginResult as LoginAuthLoginResult);
    if (!synced) {
      resetSelectionState("failed", "Authentication succeeded, but session synchronization failed.");
    }
  };

  const pollStatus = async (requestMeta: ActiveRequestMeta) => {
    if (pollingInFlightRef.current) {
      return;
    }

    pollingInFlightRef.current = true;
    try {
      const response = await fetch(
        `/api/proxy/core/api/login_auth_requests/${requestMeta.authRequestId}/status?poll_token=${encodeURIComponent(requestMeta.pollToken)}`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          cache: "no-store",
        },
      );
      const responseData = await response.json();

      if (!response.ok || !responseData?.result) {
        stopPolling();
        resetSelectionState("failed", responseData?.message || "Failed to query authentication status.");
        return;
      }

      const statusData = responseData.data as LoginAuthStatusResponseData;
      if (statusData.status === "pending") {
        return;
      }

      stopPolling();
      await resolveTerminalStatus(statusData);
    } catch (error) {
      console.error("Failed to poll login auth status:", error);
      resetSelectionState("failed", "Failed to query authentication status.");
    } finally {
      pollingInFlightRef.current = false;
    }
  };

  const selectBinding = (bindingId: number) => {
    if (viewState === "starting" || viewState === "waiting" || viewState === "syncing-session") {
      return;
    }

    setSelectedBindingId(bindingId);
    setErrorMessage("");
  };

  const startLoginAuth = async (binding: LoginAuthBindingItem) => {
    stopPolling();
    setErrorMessage("");
    setSelectedBindingId(binding.id);
    setActiveBindingId(binding.id);
    setActiveBindingName(binding.name);
    setViewState("starting");

    try {
      const safeCallbackUrl = toSafeRelativeCallbackUrl(callbackUrl);
      const response = await fetch("/api/proxy/core/api/start_login_auth/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          binding_id: binding.id,
          callback_url: safeCallbackUrl,
        }),
      });
      const responseData = await response.json();

      if (!response.ok || !responseData?.result) {
        resetSelectionState("failed", responseData?.message || "Failed to start authentication.");
        return;
      }

      const startData = responseData.data as StartLoginAuthResponseData;
      const openedWindow = window.open(startData.login_url, "_blank");
      if (!openedWindow) {
        resetSelectionState("failed", "Unable to open the authentication page. Please allow new tabs and try again.");
        return;
      }

      openedWindow.focus();

      const nextRequest = {
        authRequestId: startData.auth_request_id,
        pollToken: startData.poll_token,
        expiresAt: startData.expires_at,
      };
      setActiveRequest(nextRequest);
      setViewState("waiting");

      void pollStatus(nextRequest);
      pollingTimerRef.current = window.setInterval(() => {
        void pollStatus(nextRequest);
      }, 3000);
    } catch (error) {
      console.error("Failed to start login auth:", error);
      resetSelectionState("failed", "Failed to start authentication.");
    }
  };

  const startSelectedBindingLogin = async () => {
    if (!selectedBinding) {
      return;
    }

    await startLoginAuth(selectedBinding);
  };

  return {
    bindings,
    bindingsLoadState,
    isLoadingBindings,
    viewState,
    errorMessage,
    selectedBinding,
    selectedBindingId,
    activeBindingId,
    activeBindingName,
    activeRequest,
    selectBinding,
    reloadBindings: fetchBindings,
    startLoginAuth,
    startSelectedBindingLogin,
    resetFlow,
  };
}
