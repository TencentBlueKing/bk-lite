import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ApmRootRedirectPage({ searchParams }: PageProps) {
  redirectWithQuery('/apm/home', await searchParams);
}
