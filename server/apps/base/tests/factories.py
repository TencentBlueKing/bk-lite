import binascii
import os

import factory
from faker import Faker

from apps.base.models import User, UserAPISecret

fake = Faker()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.LazyFunction(fake.user_name)
    password = factory.django.Password("testpass123")
    domain = "domain.com"
    locale = "en"
    group_list = factory.LazyFunction(list)
    roles = factory.LazyFunction(list)


class UserAPISecretFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAPISecret

    username = factory.LazyFunction(fake.user_name)
    domain = "domain.com"
    api_secret = factory.LazyFunction(lambda: binascii.hexlify(os.urandom(32)).decode())
    team = 0
    name = factory.Sequence(lambda n: f"secret-{n}")
