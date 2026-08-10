import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ApmTracesLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/explore/traces', await searchParams);
}
