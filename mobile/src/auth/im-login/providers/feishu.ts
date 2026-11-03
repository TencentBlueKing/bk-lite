import type { AuthCodeProof } from '../types';

export const FEISHU_H5_SDK_URL = 'https://lf-scm-cn.feishucdn.com/lark/op/h5-js-sdk-1.5.44.js';
export const FEISHU_REQUEST_ACCESS_UNSUPPORTED = 103;

interface FeishuCallbackResult {
  code?: string;
  errno?: number;
  errString?: string;
}

export interface FeishuJsapi {
  requestAccess?: (options: {
    appID: string;
    scopeList: string[];
    success: (result: FeishuCallbackResult) => void;
    fail: (error: FeishuCallbackResult) => void;
  }) => void;
  requestAuthCode?: (options: {
    appId: string;
    success: (result: FeishuCallbackResult) => void;
    fail: (error: FeishuCallbackResult) => void;
  }) => void;
}

export interface FeishuHost {
  h5sdk?: {
    ready: (callback: () => void) => void;
  };
  tt?: FeishuJsapi;
}

function readErrno(error: unknown): number | null {
  if (!error || typeof error !== 'object') return null;
  const errno = (error as { errno?: unknown }).errno;
  return typeof errno === 'number' ? errno : null;
}

function callJsapi(
  invoke: (handlers: {
    success: (result: FeishuCallbackResult) => void;
    fail: (error: FeishuCallbackResult) => void;
  }) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    invoke({
      success: (result) => {
        if (result?.code) {
          resolve(result.code);
          return;
        }
        reject(result);
      },
      fail: (error) => reject(error),
    });
  });
}

async function whenFeishuReady(host: FeishuHost) {
  if (!host.h5sdk?.ready) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('feishu_ready_timeout')), 8000);
    host.h5sdk?.ready(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}

export async function requestFeishuAuthCode(appId: string, host: FeishuHost): Promise<AuthCodeProof> {
  await whenFeishuReady(host);
  const tt = host.tt;
  if (!tt) throw new Error('feishu_jsapi_missing');

  if (tt.requestAccess) {
    try {
      const code = await callJsapi((handlers) => tt.requestAccess?.({
        appID: appId,
        scopeList: [],
        ...handlers,
      }));
      return { code, evidenceMode: 'jsapi', jsapiCodeType: 'request_access' };
    } catch (error) {
      if (readErrno(error) !== FEISHU_REQUEST_ACCESS_UNSUPPORTED || !tt.requestAuthCode) {
        throw error;
      }
    }
  }

  if (!tt.requestAuthCode) throw new Error('feishu_jsapi_missing');
  const code = await callJsapi((handlers) => tt.requestAuthCode?.({
    appId,
    ...handlers,
  }));
  return { code, evidenceMode: 'jsapi', jsapiCodeType: 'request_auth_code' };
}

export function loadFeishuH5Sdk(documentRef: Document, sdkUrl = FEISHU_H5_SDK_URL): Promise<void> {
  const existing = documentRef.querySelector(`script[src="${sdkUrl}"]`);
  if (existing) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const script = documentRef.createElement('script');
    script.src = sdkUrl;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('feishu_sdk_load_failed'));
    documentRef.head.appendChild(script);
  });
}
