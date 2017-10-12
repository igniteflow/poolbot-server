import datetime
import json
import logging

from google.appengine.api import memcache
from google.appengine.api import urlfetch

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

from core.models import Player

from .decorators import ip_authorization, basic_auth

LEADERBOARD_CACHE_KEY = 'players'
LAST_UPDATED_AT_CACHE_KEY = 'last_updated_at'
PREVIOUS_LEADERBOARD_CACHE_KEY = 'players_previous'
PLAYERS_CACHE_TIMEOUT = 30  # seconds


@ip_authorization
def index(request):
    """Main page which renders the leaderboard table."""
    return render(request, 'leaderboard/index.html', {})


@ip_authorization
def api(request):
    """Internal API hit by the leaderboard index."""
    leaderboard = memcache.get(LEADERBOARD_CACHE_KEY)
    if not leaderboard:
        # update the leaderboard with the latest data and cache the result
        leaderboard = get_leaderboard_data()
        memcache.set(key=LEADERBOARD_CACHE_KEY, value=leaderboard)

    last_updated_at = memcache.get(LAST_UPDATED_AT_CACHE_KEY)
    if not last_updated_at:
        last_updated_at = datetime.datetime.now()
        memcache.set(key=LAST_UPDATED_AT_CACHE_KEY, value=last_updated_at)

    seconds_cached_for = (datetime.datetime.now() - last_updated_at).seconds
    has_expired = seconds_cached_for >= PLAYERS_CACHE_TIMEOUT

    if has_expired:
        # keep a copy of the previous state to calculate point differences
        # before it is refreshed and fetch the current state
        previous_leaderboard = leaderboard
        leaderboard = get_leaderboard_data(previous_leaderboard)


        # if the previous leaderboard and the current one are the same then don't update the cache
        # so that we always keep the last game played points difference
        has_changed = set([player['diff'] for player in leaderboard]) != set([0])
        if has_changed:
            memcache.set(key=LEADERBOARD_CACHE_KEY, value=leaderboard)
            memcache.set(key=PREVIOUS_LEADERBOARD_CACHE_KEY, value=previous_leaderboard)

            last_updated_at = datetime.datetime.now()
            memcache.set(key=LAST_UPDATED_AT_CACHE_KEY, value=last_updated_at)
        else:
            memcache.set(key=LEADERBOARD_CACHE_KEY, value=previous_leaderboard)

    context = dict(
        players=leaderboard,
        secondsLeft=PLAYERS_CACHE_TIMEOUT - (datetime.datetime.now() - last_updated_at).seconds,
        cacheLifetime=PLAYERS_CACHE_TIMEOUT
    )
    logging.info('secondsLeft: {}'.format(context['secondsLeft']))
    return JsonResponse(context)


# Utility functions

def get_leaderboard_data(previous_leaderboard=None):
    response = urlfetch.fetch(
        settings.POOLBOT_PLAYERS_API_URL,
        headers=dict(
            Authorization='Token {}'.format(settings.POOLBOT_AUTH_TOKEN),
        )
    )
    api_response = json.loads(response.content)
    leaderboard = normalise(api_response)
    leaderboard = add_diffs(leaderboard, previous_leaderboard)
    return add_leaderboard_positions(leaderboard)


def add_diffs(players, previous_leaderboard):
    for player in players:
        player['diff'] = get_diff(player, previous_leaderboard) if previous_leaderboard else 0
    return players


def get_diff(player, previous_leaderboard):
    """Returns num season_elo points gained/lost since the previous state."""
    player_previous_state = get_previous_player_state(player, previous_leaderboard)

    if player_previous_state is None:
        # EDGE CASE: the user wasn't in the previous state, so they must have been added since
        return 0

    return player['season_elo'] - player_previous_state['season_elo']


def get_previous_player_state(player, previous_leaderboard):
    for player_previous_state in previous_leaderboard:
        if player_previous_state['id'] == player['id']:
            return player_previous_state


def normalise(players):
    return [
        dict(
            name=player['real_name'] or player['name'],
            season_elo=player['season_elo'],
            id=player['slack_id'],
        )
        for player in players
        if player['active'] and player['season_match_count'] > 0
    ]


def add_leaderboard_positions(players):
    """Calculates and adds the player positions for leaderboard table listing"""

    # first sort the players by points descending
    players.sort(key=lambda x: x['season_elo'], reverse=True)

    position = 1
    for idx, player in enumerate(players):
        if idx == 0:
            # first place - no previous player to compare
            player['position'] = position
        else:
            # keep track of the previous player, if the current player has the
            # same points then they are tied so we mark with a hyphen
            previous_player = players[idx - 1]
            if previous_player['season_elo'] == player['season_elo']:
                player['position'] = '-'
            else:
                player['position'] = position

        position += 1

    return players
