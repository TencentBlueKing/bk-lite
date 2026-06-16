import * as assert from 'node:assert/strict';

let constraintsModule: Record<string, any> | undefined;

try {
  constraintsModule = await import('../src/app/cmdb/utils/fileFieldConstraints');
} catch {
  constraintsModule = undefined;
}

assert.equal(
  typeof constraintsModule?.isFileFieldType,
  'function',
  'expected shared file field constraint helper to exist'
);
assert.equal(
  typeof constraintsModule?.getFileFieldConstraintMeta,
  'function',
  'expected shared file field constraint metadata lookup to exist'
);

const { isFileFieldType, getFileFieldConstraintMeta } = constraintsModule as {
  isFileFieldType: (value: string) => boolean;
  getFileFieldConstraintMeta: (value: 'attachment' | 'image') => {
    maxCount: number;
    maxSizeMB: number;
    supportedTypeKey: string;
    behavior: {
      supportsRequired: boolean;
      supportsUnique: boolean;
      supportsSearch: boolean;
      supportsFilter: boolean;
      supportsSort: boolean;
      supportsExcelImportExport: boolean;
      supportsAutoAssociation: boolean;
    };
  };
};

assert.equal(isFileFieldType('attachment'), true);
assert.equal(isFileFieldType('image'), true);
assert.equal(isFileFieldType('str'), false);

assert.deepEqual(getFileFieldConstraintMeta('attachment'), {
  maxCount: 5,
  maxSizeMB: 50,
  supportedTypeKey: 'Model.fileFieldSupportedAttachmentTypes',
  behavior: {
    supportsRequired: false,
    supportsUnique: false,
    supportsSearch: false,
    supportsFilter: false,
    supportsSort: false,
    supportsExcelImportExport: false,
    supportsAutoAssociation: false,
  },
});

assert.deepEqual(getFileFieldConstraintMeta('image'), {
  maxCount: 5,
  maxSizeMB: 10,
  supportedTypeKey: 'Model.fileFieldSupportedImageTypes',
  behavior: {
    supportsRequired: false,
    supportsUnique: false,
    supportsSearch: false,
    supportsFilter: false,
    supportsSort: false,
    supportsExcelImportExport: false,
    supportsAutoAssociation: false,
  },
});

console.log('cmdb file field constraints test passed');
