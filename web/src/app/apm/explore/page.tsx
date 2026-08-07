import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ApmExploreRootRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/explore/traces', await searchParams);
}
