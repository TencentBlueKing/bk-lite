export type FileFieldType = 'attachment' | 'image';

export interface FileFieldBehavior {
  supportsRequired: boolean;
  supportsUnique: boolean;
  supportsSearch: boolean;
  supportsFilter: boolean;
  supportsSort: boolean;
  supportsExcelImportExport: boolean;
  supportsAutoAssociation: boolean;
}

export interface FileFieldConstraintMeta {
  maxCount: number;
  maxSizeMB: number;
  accept: string;
  supportedTypeKey: string;
  behavior: FileFieldBehavior;
}

const FILE_FIELD_BEHAVIOR: FileFieldBehavior = {
  supportsRequired: false,
  supportsUnique: false,
  supportsSearch: false,
  supportsFilter: false,
  supportsSort: false,
  supportsExcelImportExport: false,
  supportsAutoAssociation: false,
};

export const FILE_FIELD_CONSTRAINTS: Record<FileFieldType, FileFieldConstraintMeta> = {
  attachment: {
    maxCount: 5,
    maxSizeMB: 50,
    accept:
      '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.rtf,.zip,.rar,.7z,.gz,.tar,.jpg,.jpeg,.png,.gif,.webp,.bmp',
    supportedTypeKey: 'Model.fileFieldSupportedAttachmentTypes',
    behavior: FILE_FIELD_BEHAVIOR,
  },
  image: {
    maxCount: 5,
    maxSizeMB: 10,
    accept: '.jpg,.jpeg,.png,.gif,.webp,.bmp',
    supportedTypeKey: 'Model.fileFieldSupportedImageTypes',
    behavior: FILE_FIELD_BEHAVIOR,
  },
};

export const FILE_FIELD_LIMITS: Record<FileFieldType, { maxCount: number; maxSize: number; accept: string }> = {
  attachment: {
    maxCount: FILE_FIELD_CONSTRAINTS.attachment.maxCount,
    maxSize: FILE_FIELD_CONSTRAINTS.attachment.maxSizeMB * 1024 * 1024,
    accept: FILE_FIELD_CONSTRAINTS.attachment.accept,
  },
  image: {
    maxCount: FILE_FIELD_CONSTRAINTS.image.maxCount,
    maxSize: FILE_FIELD_CONSTRAINTS.image.maxSizeMB * 1024 * 1024,
    accept: FILE_FIELD_CONSTRAINTS.image.accept,
  },
};

export const isFileFieldType = (value: string): value is FileFieldType =>
  value === 'attachment' || value === 'image';

export const getFileFieldConstraintMeta = (fieldType: FileFieldType) =>
  FILE_FIELD_CONSTRAINTS[fieldType];
