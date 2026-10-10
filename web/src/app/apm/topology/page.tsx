import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ApmTopologyLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/services/topology', await searchParams);
}
