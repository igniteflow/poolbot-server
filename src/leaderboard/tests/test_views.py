import json
import mock

from django.test.client import RequestFactory

from djangae.test import TestCase

from ..views import add_leaderboard_positions, get_leaderboard_data


class GetLeaderboardDataTestCase(TestCase):

    def test_normal(self):
        with mock.patch('leaderboard.views.urlfetch.fetch') as mock_fetch:

            class Response:
                content = json.dumps([
                    dict(name='aria', real_name='Aria', season_elo=1000, slack_id=123, active=True, season_match_count=1),
                    dict(name='ned', real_name='Ned', season_elo=967, slack_id=100, active=True, season_match_count=1),
                ])

            mock_fetch.return_value = Response()
            factory = RequestFactory()
            request = factory.get('/')
            players = get_leaderboard_data(request)

            self.assertEqual(
                players,
                [
                    dict(name='Aria', season_elo=1000, id=123, diff=0, position=1),
                    dict(name='Ned', season_elo=967, id=100, diff=0, position=2),
                ]
            )


class AddLeaderboardPositionsTestCase(TestCase):
    """ sorts players by points descending and add their leaderboard position """

    def test_sorts_descending(self):
        middle, bottom, top = dict(season_elo=1100), dict(season_elo=999), dict(season_elo=1999)
        players_without_positions = [middle, bottom, top]
        players_with_positions = add_leaderboard_positions(players_without_positions)

        self.assertEqual(
            players_with_positions,
            [top, middle, bottom],
        )

    def test_draw(self):
        players = [dict(season_elo=1100), dict(season_elo=999), dict(season_elo=999), dict(season_elo=800),]
        players_with_positions = add_leaderboard_positions(players)

        self.assertEqual(
            [(p['position'], p['season_elo']) for p in players_with_positions],
            [(1, 1100), (2, 999), ('-', 999), (4, 800)],
        )
