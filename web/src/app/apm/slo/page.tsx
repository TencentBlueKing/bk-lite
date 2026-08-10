import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ApmSloLegacyRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/services/slo', await searchParams);
}
