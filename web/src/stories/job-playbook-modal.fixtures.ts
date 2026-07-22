export const jobPlaybookStoryTranslations: Record<string, string> = {
  'job.uploadPlaybook': 'Upload Playbook',
  'job.confirmUpload': 'Confirm Upload',
  'job.cancel': 'Cancel',
  'job.onlyZipAllowed': 'Only .zip, .tar.gz, or .tgz files are supported.',
  'job.dragUploadText': 'Drag a playbook archive here, or click to upload',
  'job.dragUploadHint':
    'Upload a single archive that contains the playbook bundle.',
  'job.playbookArchiveLimitHint':
    'The archive should stay within the configured size limit.',
  'job.playbookArchiveEntryLimitHint':
    'Nested files should remain within the supported entry limit.',
  'job.downloadPlaybookTemplate': 'Download Playbook Template',
  'job.versionOptional': 'Version (Optional)',
  'job.versionPlaceholder': 'e.g. v1.0.0',
  'job.organization': 'Organization',
  'job.organizationPlaceholder': 'Please select an organization',
  'job.upgradePlaybookTitle': 'Upgrade Playbook Version',
  'job.confirm': 'Confirm',
  'job.upgradeWarning':
    'Upgrading replaces the existing playbook package. Review the archive before confirming.',
  'job.selectNewZip': 'Select a new playbook archive',
  'job.currentVersionLabel': 'Current Version',
  'job.newVersionNumber': 'New Version Number',
  'job.newVersionHint':
    'Leave blank to keep the version derived from the uploaded archive.',
};

export const jobPlaybookStoryT = (key: string) =>
  jobPlaybookStoryTranslations[key] || key;
