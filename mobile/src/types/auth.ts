import { LoginUserInfo } from './user';
import type { OrganizationGroup } from '@/utils/organization';

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
  currentTeamId: string | null;
  currentTeamName: string;
  includeChildren: boolean;
  groupTree: OrganizationGroup[];
  organizationScope: string;
  applyOrganizationScope: (next: {
    teamId: string;
    teamName?: string;
    includeChildren: boolean;
  }) => boolean;
  login: (credentials: AuthLoginCredentials) => Promise<AuthLoginResult>;
  logout: () => Promise<void>;
  updateUserInfo: (updates: Partial<LoginUserInfo>) => Promise<void>;
}
