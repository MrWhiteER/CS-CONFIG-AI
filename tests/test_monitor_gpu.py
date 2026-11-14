"""NVML priority and the cached subprocess fallback, without a GPU."""

import unittest
from unittest import mock

from cs2cfg.monitor import Monitor


class GpuReading(unittest.TestCase):
    def test_nvml_is_preferred_and_supplies_vram_and_temperature(self):
        nvml = mock.Mock(api=object())
        nvml.sample.return_value = {"gpu_percent": 42, "gpu_temp_c": 65,
                                    "vram_used_mb": 2048, "vram_total_mb": 8192}
        with (mock.patch("cs2cfg.overlay.metrics.Nvml", return_value=nvml),
              mock.patch("cs2cfg.monitor._find_nvidia_smi") as find,
              mock.patch("cs2cfg.monitor.subprocess.run") as run):
            monitor = Monitor()
            result = monitor.gpu()
            self.assertEqual(monitor.gpu(), result)
            monitor.close()
        self.assertEqual(result["percent"], 42)
        self.assertEqual(result["temperature"], 65)
        self.assertEqual(result["vram_percent"], 25)
        nvml.sample.assert_called_once()
        nvml.close.assert_called_once()
        find.assert_not_called()
        run.assert_not_called()

    def test_smi_fallback_when_nvml_dll_is_missing_or_read_fails(self):
        for api in (None, object()):
            with self.subTest(api=api):
                nvml = mock.Mock(api=api)
                nvml.sample.return_value = {"gpu_percent": None, "gpu_temp_c": None}
                with (mock.patch("cs2cfg.overlay.metrics.Nvml", return_value=nvml),
                      mock.patch("cs2cfg.monitor._find_nvidia_smi", return_value="nvidia-smi.exe"),
                      mock.patch("cs2cfg.monitor.subprocess.run") as run):
                    run.return_value.stdout = "50, 1000, 8000, 70\n"
                    result = Monitor().gpu()
                self.assertEqual(result["percent"], 50)
                self.assertEqual(result["temperature"], 70)
                self.assertEqual(result["vram_percent"], 12.5)
                run.assert_called_once()

    def test_failed_fallback_is_cached_and_missing_data_remains_none(self):
        with (mock.patch("cs2cfg.overlay.metrics.Nvml", return_value=mock.Mock(api=None)),
              mock.patch("cs2cfg.monitor._find_nvidia_smi", return_value="nvidia-smi.exe"),
              mock.patch("cs2cfg.monitor.subprocess.run", side_effect=OSError("unavailable")) as run):
            monitor = Monitor()
            first, second = monitor.gpu(), monitor.gpu()
        self.assertEqual(first, second)
        self.assertIsNone(first["percent"])
        run.assert_called_once()

    def test_no_gpu_provider_returns_unavailable_without_subprocess(self):
        with (mock.patch("cs2cfg.overlay.metrics.Nvml", return_value=mock.Mock(api=None)),
              mock.patch("cs2cfg.monitor._find_nvidia_smi", return_value=None),
              mock.patch("cs2cfg.monitor.subprocess.run") as run):
            result = Monitor().gpu()
        self.assertFalse(result["available"])
        self.assertIsNone(result["temperature"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
