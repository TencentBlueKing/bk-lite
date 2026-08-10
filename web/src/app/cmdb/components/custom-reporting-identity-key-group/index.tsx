import TagCapsuleGroup from '@/components/tag-capsule-group';

export interface CustomReportingIdentityKeyGroupProps {
  keys?: string[] | null;
}

const CustomReportingIdentityKeyGroup = ({
  keys,
}: CustomReportingIdentityKeyGroupProps) => (
  <TagCapsuleGroup value={keys || []} maxVisible={3} compact />
);

export default CustomReportingIdentityKeyGroup;
