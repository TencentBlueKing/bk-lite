import factory

from apps.console_mgmt.models import Notification, UserAppSet


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    app_module = "monitor"
    content = factory.Sequence(lambda n: f"通知内容 {n}")
    source = "system"


class UserAppSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAppSet

    username = factory.Sequence(lambda n: f"user{n}")
    domain = "domain.com"
    app_config_list = factory.LazyFunction(list)
