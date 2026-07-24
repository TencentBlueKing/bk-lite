from rest_framework import serializers


class ShareExchangeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
