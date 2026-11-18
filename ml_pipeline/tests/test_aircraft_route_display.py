"""Display-cache regression checks, without inference or external API requests."""
import unittest
from unittest.mock import patch
from server.app.services.aircraft_info import AircraftInfo


class AircraftRouteDisplayTests(unittest.TestCase):
    def setUp(self):
        self.info=AircraftInfo()
        self.clock=self.enterContext(patch('server.app.services.aircraft_info.time'))
        self.clock.time.return_value=1000
        self.lookup=self.enterContext(patch('ml_pipeline.utils.route_features.route'))

    def test_missing_display_route_refreshes_after_background_lookup_populates_cache(self):
        self.lookup.return_value=(None,None)
        self.assertEqual(self.info.route(' igo147 '),(None,None))
        self.lookup.return_value=('VAID','VAPO')
        self.clock.time.return_value=1005
        self.assertEqual(self.info.route('IGO147'),(None,None))
        self.clock.time.return_value=1010
        self.assertEqual(self.info.route('IGO147'),('VAID','VAPO'))
        self.lookup.assert_called_with('IGO147',fetch=False)
        self.assertEqual(self.lookup.call_count,2)

    def test_partial_route_refreshes_and_known_route_keeps_existing_ten_minute_cache(self):
        self.lookup.return_value=('VABB',None)
        self.info.route('TEST123')
        self.lookup.return_value=('VABB','OMAA')
        self.clock.time.return_value=1011
        self.assertEqual(self.info.route('TEST123'),('VABB','OMAA'))
        self.lookup.return_value=('OTHER','OTHER')
        self.clock.time.return_value=1300
        self.assertEqual(self.info.route('TEST123'),('VABB','OMAA'))
        self.assertEqual(self.lookup.call_count,2)

    def test_empty_identifier_does_not_lookup_and_error_miss_can_recover(self):
        self.assertEqual(self.info.route(None),(None,None))
        self.lookup.assert_not_called()
        self.lookup.side_effect=OSError('temporary cache read error')
        self.assertEqual(self.info.route('TEST123'),(None,None))
        self.lookup.side_effect=None
        self.lookup.return_value=('VABB','OMAA')
        self.clock.time.return_value=1010
        self.assertEqual(self.info.route('TEST123'),('VABB','OMAA'))
