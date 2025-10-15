

export type AuthStep = 'login' | 'reset-password' | 'otp-verification';

export interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitializing: boolean;
  login: (token: string) => void;
  logout: () => Promise<void>;
}