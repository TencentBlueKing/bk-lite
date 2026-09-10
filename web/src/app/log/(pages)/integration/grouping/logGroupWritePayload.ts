import { FilterItem, GroupInfo } from '@/app/log/types/integration';

export const buildLogGroupSubmitPayload = ({
  values,
  term,
  conditions,
  id,
  isBuiltIn
}: {
  values: GroupInfo;
  term: string | null;
  conditions: FilterItem[];
  id: GroupInfo['id'];
  isBuiltIn: boolean;
}): GroupInfo => {
  const params: GroupInfo = {
    ...values,
    id
  };
  if (isBuiltIn || !term) {
    params.rule = {};
    return params;
  }
  params.rule = {
    mode: term,
    conditions
  };
  return params;
};
