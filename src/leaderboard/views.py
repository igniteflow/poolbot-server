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
LAST_UPDATED_CACHE_KEY = 'last_updated'
PREVIOUS_LEADERBOARD_CACHE_KEY = 'players_previous'
PLAYERS_CACHE_TIMEOUT = 30


@ip_authorization
def index(request):
    """Main page which renders the leaderboard table."""
    return render(request, 'leaderboard/index.html', {})


@ip_authorization
def api(request):
    """Internal API hit by the leaderboard index."""

    leaderboard = memcache.get(LEADERBOARD_CACHE_KEY)
    last_updated = memcache.get(LAST_UPDATED_CACHE_KEY)

    has_expired = True
    cached_for = 0
    if last_updated:
        cached_for = (datetime.datetime.now() - last_updated).seconds
        has_expired = cached_for >= PLAYERS_CACHE_TIMEOUT

    if leaderboard and has_expired:
        # keep a copy of the previous state to calculate point differences
        memcache.add(key=PREVIOUS_LEADERBOARD_CACHE_KEY, value=leaderboard)

    if has_expired:
        # update the leaderboard with the latest data and cache the result
        leaderboard = get_leaderboard_from_api(leaderboard)
        memcache.add(key=LEADERBOARD_CACHE_KEY, value=leaderboard)

        # keep a note of when we updated the leaderboard so that we know
        # when to refresh the cache
        last_updated = datetime.datetime.now()
        memcache.add(key=LAST_UPDATED_CACHE_KEY, value=last_updated)

    cached_for = (datetime.datetime.now() - last_updated).seconds
    logging.info('cached_for: {}'.format(cached_for))
    return JsonResponse(
        dict(
            players=leaderboard,
            secondsLeft=cached_for,
            cacheLifetime=PLAYERS_CACHE_TIMEOUT
        )
    )


# Utility functions

def get_leaderboard_from_api(previous_leaderboard=None):
    response = urlfetch.fetch(
        settings.POOLBOT_PLAYERS_API_URL,
        headers=dict(
            Authorization='Token {}'.format(settings.POOLBOT_AUTH_TOKEN),
        )
    )
    players = json.loads(response.content)

    leaderboard = [
        dict(
            name=player['real_name'] or player['name'],
            season_elo=player['season_elo'],
            diff=get_diff(player, previous_leaderboard) if previous_leaderboard else 0,
            slack_id=player['slack_id'],
        )
        for player in players
        if player['active'] and player['season_match_count'] > 0
    ]
    leaderboard.sort(key=lambda x: x['season_elo'], reverse=True)

    return add_leaderboard_positions(leaderboard)


def get_diff(player, previous_leaderboard):
    """Returns num season_elo points gained/lost since the previous state."""
    player_previous_state = get_previous_player_state(player, previous_leaderboard)
    if player_previous_state:
        return player['season_elo'] - player_previous_state['season_elo']
    return 0


def get_previous_player_state(player, previous_leaderboard):
    for player_previous_state in previous_leaderboard:
        if player_previous_state['slack_id'] == player['slack_id']:
            return player_previous_state


def add_leaderboard_positions(players):
    """Calculates and adds the player positions for leaderboard table listing."""
    position = 1
    for idx, player in enumerate(players):
        player['id'] = idx
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
