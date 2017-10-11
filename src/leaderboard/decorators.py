import base64
import logging

from decorator import decorator
from django.http import HttpResponse
from django.conf import settings


@decorator
def ip_authorization(func, *args, **kwargs):
    """Limit requests to whitelised IP addresses if configured."""
    if not settings.AUTHORISED_LEADERBOARD_IPS:
        logging.warning(
            'No AUTHORISED_LEADERBOARD_IPS defined, board is publicly viewable')
        return func(*args, **kwargs)

    request = args[0]
    request_ip = request.META['REMOTE_ADDR']
    if request_ip in settings.AUTHORISED_LEADERBOARD_IPS:
        return func(*args, **kwargs)
    else:
        logging.error(
            'Leaderboard request received from unrecognised IP {} not in {}'.format(
                request_ip,
                settings.AUTHORISED_LEADERBOARD_IPS,
            )
        )
        return HttpResponse(status=401)


@decorator
def basic_auth(func, request, *args, **kwargs):
    realm = ""
    if 'HTTP_AUTHORIZATION' in request.META:
        auth = request.META['HTTP_AUTHORIZATION'].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                uname, passwd = base64.b64decode(auth[1]).split(':')
                if uname == settings.LEADERBOARD_BASIC_AUTH_USERNAME and passwd == settings.LEADERBOARD_BASIC_AUTH_PASSWORD:
                    return func(request, *args, **kwargs)

    # Either they did not provide an authorization header or
    # something in the authorization attempt failed. Send a 401
    # back to them to ask them to authenticate.
    response = HttpResponse()
    response.status_code = 401
    response['WWW-Authenticate'] = 'Basic realm="%s"' % realm
    return response
