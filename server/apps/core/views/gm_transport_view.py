from django.http import HttpResponseNotAllowed, JsonResponse

from apps.core.services.gm_transport import public_payload
from apps.core.utils.exempt import api_exempt


@api_exempt
def gm_transport_public(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"result": True, "data": public_payload()})
