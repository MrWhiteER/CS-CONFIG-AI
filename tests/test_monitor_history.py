"""The System graph's history: kept from app start, and across a restart."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import monitor
from cs2cfg.monitor import HISTORY_LENGTH, SAMPLE_SECONDS, SERIES, Monitor


def reading(cpu=10.0, gpu=20.0, ram=30.0, vram=40.0, temp=55.0):
    return {"cpu": {"percent": cpu}, "ram": {"percent": ram},
            "gpu": {"percent": gpu, "vram_percent": vram, "temperature": temp}}


class History(unittest.TestCase):
    def setUp(self):
        self.no_temps = mock.patch.object(Monitor, "_temperatures",
                                          staticmethod(lambda gpu: {"temp-cpu": None,
                                                                    "temp-gpu": gpu.get("temperature"),
                                                                    "temp-system": None}))
        self.no_temps.start()
        self.addCleanup(self.no_temps.stop)

    def test_every_series_shares_one_timeline_and_is_capped(self):
        m = Monitor()
        for i in range(HISTORY_LENGTH + 5):
            m._record(reading(cpu=i), 1000 + i * SAMPLE_SECONDS)
        self.assertEqual({len(m.history[k]) for k in SERIES}, {HISTORY_LENGTH})
        self.assertEqual(m.history["cpu"][-1], HISTORY_LENGTH + 4)
        self.assertEqual(m.history["temp-gpu"][-1], 55.0)

    def test_missed_time_is_a_gap_not_a_squeeze(self):
        m = Monitor()
        m._record(reading(cpu=1), 1000)
        m._record(reading(cpu=2), 1000 + 4 * SAMPLE_SECONDS)
        self.assertEqual(m.history["cpu"], [1, None, None, None, 2])

    def test_polls_read_the_background_samples_without_adding_any(self):
        m = Monitor()
        m._record(reading(cpu=12), time.time())
        m._thread = mock.Mock(is_alive=lambda: True)
        with mock.patch.object(m, "_measure") as measure, mock.patch.object(m, "game", return_value={}):
            first, second = m.sample(), m.sample()
        measure.assert_not_called()
        self.assertEqual(first["history"]["cpu"], [12])
        self.assertEqual(first["at"], second["at"])
        self.assertEqual(second["cpu"]["percent"], 12)

    def test_without_the_sampler_a_poll_still_measures(self):
        m = Monitor()
        with mock.patch.object(m, "_measure", return_value=reading(cpu=7)), \
                mock.patch.object(m, "game", return_value={}):
            out = m.sample()
        self.assertEqual(out["history"]["cpu"], [7])

    def test_a_restart_picks_the_window_back_up(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "history.json"
            first = Monitor()
            first._store = store
            now = time.time()
            for i in range(10):
                first._record(reading(cpu=i), now - 20 + i * SAMPLE_SECONDS)
            first.save()

            second = Monitor()
            second._load(store)
            self.assertEqual(second.history["cpu"], list(range(10)))
            second._record(reading(cpu=99), now + 2)
            # The seconds the app was closed are blank, then the new reading.
            self.assertEqual(second.history["cpu"][-1], 99)
            self.assertIn(None, second.history["cpu"][10:-1])
            self.assertEqual({len(second.history[k]) for k in SERIES}, {len(second.history["cpu"])})

    def test_an_old_saved_window_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "history.json"
            store.write_text(json.dumps({"at": time.time() - 3600,
                                         "history": {"cpu": [1, 2, 3]}}), encoding="utf-8")
            m = Monitor()
            m._load(store)
            self.assertEqual(m.history["cpu"], [])

    def test_a_damaged_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / "history.json"
            store.write_text("{not json", encoding="utf-8")
            m = Monitor()
            m._load(store)
            self.assertEqual(m.history["cpu"], [])

    def test_the_sampler_fills_history_before_any_page_asks(self):
        m = Monitor()
        with mock.patch.object(monitor, "SAMPLE_SECONDS", 0.01), \
                mock.patch.object(m, "_measure", return_value=reading()), \
                mock.patch.object(m, "cpu_percent"):
            m.start()
            deadline = time.time() + 5
            while len(m.history["cpu"]) < 3 and time.time() < deadline:
                time.sleep(0.02)
            m.stop()
        self.assertGreaterEqual(len(m.history["cpu"]), 3)


if __name__ == "__main__":
    unittest.main()
