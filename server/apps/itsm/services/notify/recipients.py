from django.db.models import Q
from django.utils import timezone

from apps.system_mgmt.models import User


def active_users(domain, *, now=None):
    return User.objects.filter(domain=domain, disabled=False).filter(
        Q(account_expires_at__isnull=True) | Q(account_expires_at__gt=now or timezone.now())
    )
