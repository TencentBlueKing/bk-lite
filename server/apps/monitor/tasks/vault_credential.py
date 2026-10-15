from celery import shared_task

from apps.monitor.services.vault_credential.reconcile import reconcile_vault_credentials, refresh_credential_refs


@shared_task
def refresh_vault_credential_refs(credential_ids):
    return refresh_credential_refs(credential_ids)


@shared_task
def reconcile_vault_credentials_task():
    return reconcile_vault_credentials()
