export type LoginAuthRequestStatus = 'pending' | 'success' | 'failed' | 'expired' | 'cancelled';
export type LoginAuthResultStatus = 'success' | 'failed' | 'cancelled' | 'expired';

export type LoginAuthValidationViewState =
  | 'idle'
  | 'starting'
  | 'waiting'
  | 'syncing-session'
  | 'failed'
  | 'expired'
  | 'cancelled';

export interface LoginAuthBindingItem {
  id: number;
  name: string;
  icon: string;
  description: string;
  provider_key: string;
}

export interface StartLoginAuthResponseData {
  auth_request_id: string;
  poll_token: string;
  login_url: string;
  expires_at: string;
}

export interface LoginAuthLoginResult {
  id?: string | number;
  username?: string;
  token?: string;
  locale?: string;
  timezone?: string;
  display_name?: string;
  domain?: string;
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  password_expiry_reminder?: string;
  redirect_url?: string;
  require_otp?: boolean;
  challenge_id?: string;
  qr_code?: string;
}

export interface LoginAuthStatusResponseData {
  status: LoginAuthRequestStatus;
  error_message?: string;
  expires_at?: string;
  completed_at?: string | null;
  login_result?: LoginAuthLoginResult;
}

export interface LoginAuthResultPageSearchParams {
  status?: string;
  message?: string;
}
