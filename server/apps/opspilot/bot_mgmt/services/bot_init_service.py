from django.utils.translation import gettext as _

from apps.opspilot.models import RasaModel


class BotInitService:
    def __init__(self, owner):
        self.owner = owner.username

    def init(self):
        rasa_model, created = RasaModel.objects.update_or_create(
            name="Core Model", created_by=self.owner, defaults={"description": _("Core Model")}
        )
        if created:
            with open("support-files/data/ops-pilot.tar.gz", "rb") as f:
                rasa_model.model_file.save("core_model.tar.gz", f)
            rasa_model.save()

        # Bot.objects.get_or_create(
        #     name="OpsPilot",
        #     defaults={
        #         "created_by": self.owner,
        #         "rasa_model": rasa_model,
        #         "introduction": "Intelligent Operations Assistant",
        #     },
        # )
