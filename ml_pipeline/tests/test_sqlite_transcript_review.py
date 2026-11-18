"""Real SQLite insert ID: transcript review must not depend on PostgreSQL."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.app.services import database as db_module
from server.app.services import speech_service as speech_module
from server.app.services import clearance_service as clearance_module


class TranscriptReviewPersistence(unittest.TestCase):
    def test_sqlite_returns_distinct_ids_and_review_finds_the_record(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store=db_module.Database()
            with patch.object(db_module,'AUDIT_DATABASE',Path(temp)/'audit.sqlite3'), \
                 patch.object(db_module,'DATABASE_URL',''), \
                 patch.object(speech_module,'database',store), \
                 patch.object(clearance_module,'database',store):
                store.initialise()
                service=speech_module.SpeechService()
                flights=[dict(icao24='de0101',callsign='IGO101',altitudeFt=5000,onGround=False)]
                first=service.process_text('IGO101 request departure',flights,role='pilot')
                second=service.process_text('IGO101 request departure',flights,role='pilot')
                self.assertIsInstance(first['transcriptionId'],int)
                self.assertNotEqual(first['transcriptionId'],second['transcriptionId'])
                reviewed=service.review(first['transcriptionId'],'IGO101 request departure','pilot',flights)
                self.assertEqual(reviewed['reviewOf'],first['transcriptionId'])
                self.assertEqual(reviewed['modelId'],'reviewed-radio')
                self.assertEqual(len(store.transcription_history(20)),3)


if __name__=='__main__':unittest.main()
