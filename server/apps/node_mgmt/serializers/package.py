from rest_framework import serializers
from apps.node_mgmt.models.package import PackageVersion


class PackageVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageVersion
        fields = '__all__'
