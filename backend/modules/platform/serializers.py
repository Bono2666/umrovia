from rest_framework import serializers

from modules.platform.models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    consent = serializers.BooleanField(write_only=True)
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = ContactMessage
        fields = ["name", "company", "email", "phone", "topic", "message", "consent", "website"]
        extra_kwargs = {"message": {"min_length": 20, "max_length": 4000}}

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("Persetujuan pemrosesan pesan wajib diberikan.")
        return value

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError("Pesan tidak dapat diproses.")
        return value

    def create(self, validated_data):
        validated_data.pop("consent")
        validated_data.pop("website", None)
        return super().create(validated_data)
