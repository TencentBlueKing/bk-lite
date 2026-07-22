import { LoginUserInfo } from './user';

export type AuthStep = 'login' | 'reset-password' | 'otp-verification';

export interface AuthLoginCredentials {
  username: string;
  password: string;
  domain: string;
}

export type AuthLoginResult =
  | { status: 'success' }
  | { status: 'invalid-credentials'; message?: string }
  | { status: 'otp-required' }
  | { status: 'password-reset-required' }
  | { status: 'service-unavailable' };

export interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitializing: boolean;
  userInfo: LoginUserInfo | null;
  login: (credentials: AuthLoginCredentials) => Promise<AuthLoginResult>;
  logout: () => Promise<void>;
  updateUserInfo: (updates: Partial<LoginUserInfo>) => Promise<void>;
}
