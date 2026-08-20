import LoginAuthResultContent from './LoginAuthResultContent';
import type { LoginAuthResultPageSearchParams, LoginAuthResultStatus } from '../login-auth/types';

interface LoginAuthResultPageProps {
  searchParams: Promise<LoginAuthResultPageSearchParams>;
}

function normalizeStatus(status?: string): LoginAuthResultStatus {
  if (status === 'success' || status === 'cancelled' || status === 'expired') {
    return status;
  }
  return 'failed';
}

export default async function LoginAuthResultPage({ searchParams }: LoginAuthResultPageProps) {
  const resolvedSearchParams = await searchParams;
  const status = normalizeStatus(resolvedSearchParams.status);

  return (
    <LoginAuthResultContent
      status={status}
      message={resolvedSearchParams.message}
    />
  );
}
