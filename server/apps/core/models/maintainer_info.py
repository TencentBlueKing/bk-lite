from django.db import models
from django.utils.translation import gettext_lazy as _

SYSTEM_MAINTAINER = "system"
DEFAULT_MAINTAINER_DOMAIN = "domain.com"


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def maintainer_kwargs(actor_context=None, *, operator=None, domain=None, include_created=True):
    """Build MaintainerInfo field values from an actor context or explicit operator.

    User-facing writes should pass actor_context; background jobs fall back to ``system``.
    """
    ctx = actor_context or {}
    username = _first_non_empty(operator, ctx.get("username")) or SYSTEM_MAINTAINER
    actor_domain = _first_non_empty(domain, ctx.get("domain")) or DEFAULT_MAINTAINER_DOMAIN
    fields = {
        "updated_by": username,
        "updated_by_domain": actor_domain,
    }
    if include_created:
        fields["created_by"] = username
        fields["domain"] = actor_domain
    return fields


class MaintainerInfo(models.Model):
    """
    Add maintainer fields to another models.
    """

    class Meta:
        verbose_name = _("Maintainer Fields")
        abstract = True

    created_by = models.CharField(_("Creator"), max_length=32, default="")
    updated_by = models.CharField(_("Updater"), max_length=32, default="")
    domain = models.CharField(_("Domain"), max_length=100, default="domain.com")
    updated_by_domain = models.CharField(_("updated by domain"), max_length=100, default="domain.com")
