export interface NamespaceItem {
  id: number;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  domain: string;
  updated_by_domain: string;
  name: string;
  account: string;
  password: string;
  describe: string;
  is_active: boolean;
}

export interface TagItem {
  id: number;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  domain: string;
  updated_by_domain: string;
  tag_id: string;
  name: string;
  desc: string | null;
  build_in: boolean;
}

export interface NamespaceOperateModalProps {
  open: boolean;
  currentRow?: NamespaceItem;
  onClose: () => void;
  onSuccess?: () => void;
}
