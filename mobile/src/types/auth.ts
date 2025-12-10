import { LoginUserInfo } from './user';

export type AuthStep = 'login' | 'reset-password' | 'otp-verification';

export interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitializing: boolean;
  userInfo: LoginUserInfo | null;
  login: (token: string, userInfo: LoginUserInfo) => Promise<void>;
  logout: () => Promise<void>;
  updateUserInfo: (updates: Partial<LoginUserInfo>) => Promise<void>;
}