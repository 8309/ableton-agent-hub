import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf
from ableton_bridge.audio_similarity import analyze, preserve_cache, rank_sounds
from ableton_bridge.mcp_creative import SearchSounds, search_sounds


class AudioSimilarityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "catalog.db"
        sqlite3.connect(self.db).close()

    def audio(self, name="tone.wav", seconds=1, frequency=440, stereo=False):
        t = np.arange(int(seconds * 16000)) / 16000
        samples = 0.5 * np.sin(2 * np.pi * frequency * t)
        if stereo:
            samples = np.column_stack([samples, -samples])
        path = self.root / name
        sf.write(path, samples, 16000)
        return path

    def test_metrics_antiphase_formats_and_cache(self):
        for ext in ("wav", "aiff", "flac"):
            p = self.audio("tone." + ext, stereo=True)
            a = analyze(p, self.db)
            self.assertEqual(a["status"], "ok")
            self.assertAlmostEqual(a["rms"], 0.5 / np.sqrt(2), places=3)
            self.assertAlmostEqual(a["spectral_centroid_hz"], 440, delta=5)
            self.assertFalse(a["cache_hit"])
            self.assertTrue(analyze(p, self.db)["cache_hit"])
            self.audio("tone." + ext, frequency=880)
            self.assertFalse(analyze(p, self.db)["cache_hit"])

    def test_bounds_silence_invalid_and_rebuild(self):
        p = self.audio(seconds=31)
        a = analyze(p, self.db)
        self.assertEqual(a["analyzed_seconds"], 30)
        self.assertTrue(a["partial_file"])
        self.assertEqual(analyze(self.root / "absent.wav", self.db)["reason"], "file_missing")
        p.write_bytes(b"broken")
        self.assertEqual(analyze(p, self.db)["reason"], "decode_failed")
        silent = self.root / "silent.wav"
        sf.write(silent, np.zeros(1000), 16000)
        self.assertIsNone(analyze(silent, self.db)["spectral_centroid_hz"])
        self.assertFalse(rank_sounds(self.db, silent)["ok"])
        with closing(sqlite3.connect(self.root / "new.db")) as new, new:
            preserve_cache(new, self.db)
            self.assertEqual(new.execute("SELECT count(*) FROM waveform_cache").fetchone()[0], 2)

    def test_ranking_candidates_and_schema(self):
        reference = self.audio("ref.wav")
        near, far = self.audio("near.wav", frequency=445), self.audio("far.wav", frequency=6000)
        rows = [{"path": str(p), "name": p.name} for p in (far, near, self.root / "missing.wav")]
        with patch("ableton_bridge.sound_catalog_db.search_database", return_value=rows):
            result = rank_sounds(self.db, reference, limit=2)
            self.assertEqual(result["resources"][0]["name"], "near.wav")
            self.assertEqual(len(result["unranked"]), 1)
            again = search_sounds({"reference_audio": str(reference), "limit": 2}, database_path=self.db)
            self.assertTrue(again["reference"]["cache_hit"])
            self.assertTrue(all(x["waveform"]["cache_hit"] for x in again["resources"]))
            json.dumps(again, allow_nan=False)
        with self.assertRaises(ValueError):
            SearchSounds(reference_audio="relative.wav")
        with self.assertRaises(ValueError):
            rank_sounds(self.db, reference, candidate_limit=65)
