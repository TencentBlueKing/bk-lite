import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ApmPoliciesLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/events/policies', await searchParams);
}
