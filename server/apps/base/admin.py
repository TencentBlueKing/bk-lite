from django.contrib import admin
from .models import UserAPISecret, User


@admin.register(UserAPISecret)
class UserAPISecretAdmin(admin.ModelAdmin):
    list_display = ("username", "api_secret_preview", "team")
    search_fields = ('username', 'team')
    readonly_fields = ("api_secret_preview",)
    exclude = ("api_secret",)

    @admin.display(description="API Secret")
    def api_secret_preview(self, obj):
        return obj.get_api_secret_preview()

    def save_model(self, request, obj, form, change):
        if not obj.api_secret:
            obj.api_secret = UserAPISecret.generate_api_secret()
        obj.api_secret = UserAPISecret.hash_api_secret(obj.api_secret)
        super().save_model(request, obj, form, change)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    list_filter = ('is_staff', 'is_active', 'groups')
