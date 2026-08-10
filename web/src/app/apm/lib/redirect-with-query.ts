import { redirect } from 'next/navigation';

type SearchParams = Record<string, string | string[] | undefined>;

const toQueryString = (searchParams: SearchParams): string => {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item != null) query.append(key, item);
      });
    } else if (value != null) {
      query.set(key, value);
    }
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
};

/** Permanent-style app redirect that preserves query string. */
export const redirectWithQuery = (
  targetPath: string,
  searchParams: SearchParams = {},
): never => {
  redirect(`${targetPath}${toQueryString(searchParams)}`);
};
