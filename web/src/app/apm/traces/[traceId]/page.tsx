import { redirectWithQuery } from '@/app/apm/lib/redirect-with-query';

type PageProps = {
  params: Promise<{ traceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ApmTraceDetailLegacyRedirectPage({
  params,
  searchParams,
}: PageProps) {
  const { traceId } = await params;
  redirectWithQuery(`/apm/explore/traces/${traceId}`, await searchParams);
}
