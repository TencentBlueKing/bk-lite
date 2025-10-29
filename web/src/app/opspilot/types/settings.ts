export interface QuotaData {
  label: string;
  usage: number;
  total: number;
  unit: string;
}

export interface QuotaModalProps {
  visible: boolean;
  onConfirm: (values: any) => Promise<void>;
  onCancel: () => void;
  mode: 'add' | 'edit';
  initialValues?: any;
}

export interface TargetOption {
  id: string;
  name: string;
}
