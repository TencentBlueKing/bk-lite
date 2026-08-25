import type { CustomReportingOnboardingDocument } from '@/app/cmdb/types/customReporting';

export const buildCustomReportingCurlPayload = (
  documentData: CustomReportingOnboardingDocument,
) => {
  const documentedInstance = documentData.examples?.instances?.instances?.[0];
  if (documentedInstance && Object.keys(documentedInstance).length > 0) {
    return { instances: [documentedInstance] };
  }

  const configuredIdentityKeys = documentData.identity_keys?.length
    ? documentData.identity_keys
    : ['inst_name'];
  const identityKeys = configuredIdentityKeys.filter((key) => key !== 'organization');
  const fallbackKeys = identityKeys.length > 0 ? identityKeys : ['inst_name'];
  const fallbackInstance = fallbackKeys.reduce<Record<string, string>>((acc, key) => {
    acc[key] = `<${key}>`;
    return acc;
  }, {});
  return { instances: [fallbackInstance] };
};
