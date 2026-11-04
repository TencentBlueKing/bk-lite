export type EvidenceMode = 'oauth' | 'jsapi';

export type JsapiCodeType = 'request_access' | 'request_auth_code';

export type ImContainer = 'feishu' | 'wecom';

export type SilentLoginMode = 'jsapi' | 'oauth';

export interface ClientLoginDescriptor {
  evidence_modes?: string[];
  jsapi?: {
    app_id?: string;
  };
}

export interface PublicLoginBinding {
  id: number;
  name: string;
  provider_key: string;
  icon?: string;
  description?: string;
  order?: number;
  client_login?: ClientLoginDescriptor;
}

export interface AuthCodeProof {
  code: string;
  evidenceMode: EvidenceMode;
  jsapiCodeType?: JsapiCodeType;
}

export interface ExternalLoginResult {
  id?: string | number;
  username?: string;
  token?: string;
  locale?: string;
  timezone?: string;
  domain?: string;
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  require_otp?: boolean;
  qrcode?: boolean;
}

export interface LoginNotice {
  reason: 'jsapi_failed' | 'exchange_failed' | 'session_failed' | 'oauth_failed' | 'oauth_cancelled' | 'otp_required' | 'password_reset_required';
  name: string;
}

export type SilentLoginOutcome =
  | { status: 'skipped' }
  | { status: 'success'; token: string }
  | { status: 'redirecting' }
  | { status: 'degraded'; notice: LoginNotice };

export interface OAuthPending {
  authRequestId: string;
  pollToken: string;
  bindingName: string;
}
