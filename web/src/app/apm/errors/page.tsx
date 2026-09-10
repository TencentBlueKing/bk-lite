import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ApmErrorsLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/explore/errors', await searchParams);
}
