"""Exporting one skin preview through a tool the user installed -- never
run for real here. Every subprocess call is a stub.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import skin_render  # noqa: E402


class ToolPath(unittest.TestCase):
    def test_nothing_configured_is_not_found(self):
        self.assertIsNone(skin_render.tool_path({}))

    def test_a_configured_path_that_does_not_exist_is_not_found(self):
        self.assertIsNone(skin_render.tool_path({"source2viewer_path": r"C:\nope\tool.exe"}))

    def test_a_configured_path_that_exists_is_found(self, ):
        with mock.patch.object(skin_render.Path, "is_file", return_value=True):
            found = skin_render.tool_path({"source2viewer_path": r"C:\tools\s2v.exe"})
        self.assertIsNotNone(found)

    def test_status_reports_configured_without_found(self):
        result = skin_render.status({"source2viewer_path": r"C:\nope\tool.exe"})
        self.assertTrue(result["configured"])
        self.assertFalse(result["found"])

    def test_status_with_nothing_set_is_not_configured(self):
        result = skin_render.status({})
        self.assertFalse(result["configured"])
        self.assertFalse(result["found"])


class Rendering(unittest.TestCase):
    def test_a_successful_export_returns_the_glb_bytes(self):
        def fake_run(args, timeout=None, capture_output=None):
            out_dir = Path(args[args.index("-o") + 1])
            (out_dir / "model.glb").write_bytes(b"gltf-bytes")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            data = skin_render.render(Path("fake_dir.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl",
                                      Path("s2v.exe"))
        self.assertEqual(data, b"gltf-bytes")

    def test_nothing_survives_after_the_call_returns(self):
        """The temp directory this writes into is gone once render()
        returns -- that is the whole ephemeral guarantee."""
        captured = {}

        def fake_run(args, timeout=None, capture_output=None):
            out_dir = Path(args[args.index("-o") + 1])
            captured["dir"] = out_dir
            (out_dir / "model.glb").write_bytes(b"x")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            skin_render.render(Path("fake_dir.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl",
                               Path("s2v.exe"))
        self.assertFalse(captured["dir"].exists())

    def test_a_model_path_already_compiled_is_not_doubly_suffixed(self):
        seen = {}

        def fake_run(args, timeout=None, capture_output=None):
            seen["vpk_filepath"] = args[args.index("--vpk_filepath") + 1]
            out_dir = Path(args[args.index("-o") + 1])
            (out_dir / "m.glb").write_bytes(b"x")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl_c", Path("s2v.exe"))
        self.assertEqual(seen["vpk_filepath"], "weapons/models/ak47/weapon_rif_ak47.vmdl_c")

    def test_a_nonzero_exit_is_a_render_error_not_a_crash(self):
        def fake_run(args, timeout=None, capture_output=None):
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"bad vpk path")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl", Path("s2v.exe"))

    def test_a_timeout_is_a_render_error_not_an_indefinite_hang(self):
        with mock.patch.object(skin_render.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("s2v", 60)):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl", Path("s2v.exe"))

    def test_producing_nothing_is_a_render_error(self):
        def fake_run(args, timeout=None, capture_output=None):
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl", Path("s2v.exe"))

    def test_the_executable_itself_missing_is_a_render_error(self):
        with mock.patch.object(skin_render.subprocess, "run", side_effect=OSError("not found")):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl", Path("s2v.exe"))


def _fake_index(paths):
    return {p: object() for p in paths}


class ResolvingTheTexture(unittest.TestCase):
    """What actually gives a skin its colour, not just its shape.

    A weapon model's own material is the bare factory default -- the paint
    is a separate file, found one of two ways depending on how old the
    skin is. See skin_render.texture_path's docstring.
    """

    def test_a_newer_skin_is_found_directly_by_name(self):
        index = _fake_index([
            "items/assets/paintkits/set_spy_tech/ak47_autoexec_camo_albedo_texture_tga_5e17359d.vtex_c",
            "materials/models/weapons/customization/paints/vmats/so_red.vmat_c",
        ])
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"),
                                              "weapon_ak47", "ak47_autoexec_camo")
        self.assertEqual(found.path, "items/assets/paintkits/set_spy_tech/"
                                     "ak47_autoexec_camo_albedo_texture_tga_5e17359d.vtex_c")

    def test_a_newer_skin_is_never_tiled(self):
        """A composite-system skin is always one image mapped once over the
        whole weapon -- there is no pattern/tiled variant of it."""
        index = _fake_index([
            "items/assets/paintkits/set_spy_tech/ak47_autoexec_camo_albedo_texture_tga_5e17359d.vtex_c",
        ])
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"),
                                              "weapon_ak47", "ak47_autoexec_camo")
        self.assertFalse(found.tiled)

    def test_an_older_skin_falls_back_to_resolving_its_material(self):
        index = _fake_index([
            "materials/models/weapons/customization/paints/vmats/aq_oiled.vmat_c",
        ])
        vmat_dump = (
            '        {\n'
            '                m_name = "g_tColor"\n'
            '                m_pValue = resource:"materials/default/default_weapon_color_tga_a59dc9c7.vtex"\n'
            '        },\n'
            '        {\n'
            '                m_name = "g_tPattern"\n'
            '                m_pValue = resource:"materials/models/weapons/customization/paints/'
            'antiqued/oiled_psd_9f35e709.vtex"\n'
            '        },\n'
            '        F_PAINT_STYLE = 7\n'
        )
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"),
                                              "weapon_ak47", "aq_oiled")
        self.assertEqual(found.path, "materials/models/weapons/customization/paints/"
                                     "antiqued/oiled_psd_9f35e709.vtex_c")

    def test_paint_style_7_is_tiled(self):
        """Style 7 ("Gunsmith") is the small patina/case-hardened pattern
        meant to repeat across the model -- confirmed against the real
        Case Hardened material."""
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        vmat_dump = ('m_name = "g_tPattern"\nm_pValue = resource:"materials/x.vtex"\n'
                    'F_PAINT_STYLE = 7\n')
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertTrue(found.tiled)

    def test_paint_style_6_custom_paint_job_is_not_tiled(self):
        """Style 6 ("Custom Paint Job" -- Workshop designs like Kill
        Confirmed or Asiimov) is one image mapped 1:1 over the model.
        Tiling it produced a shattered-looking mess, not a soft error --
        confirmed by rendering the real Kill Confirmed material both ways."""
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        vmat_dump = ('m_name = "g_tPattern"\nm_pValue = resource:"materials/x.vtex"\n'
                    'F_PAINT_STYLE = 6\n')
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertFalse(found.tiled)

    def test_an_unrecognised_paint_style_defaults_to_not_tiled(self):
        """Direct 1:1 mapping is the common case; an unknown style should
        not silently start tiling a full-coverage image."""
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        vmat_dump = ('m_name = "g_tPattern"\nm_pValue = resource:"materials/x.vtex"\n'
                    'F_PAINT_STYLE = 2\n')
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertFalse(found.tiled)

    def test_no_paint_style_found_at_all_defaults_to_not_tiled(self):
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        vmat_dump = 'm_name = "g_tPattern"\nm_pValue = resource:"materials/x.vtex"\n'
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertFalse(found.tiled)

    def test_g_tpattern_is_preferred_over_the_shared_default_g_tcolor(self):
        """g_tColor is the generic base every weapon's default material
        points at; g_tPattern is the skin's own art. Picking g_tColor would
        show the same flat default on every legacy skin."""
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        vmat_dump = (
            'm_name = "g_tColor"\n'
            'm_pValue = resource:"materials/default/default_weapon_color.vtex"\n'
            'm_name = "g_tPattern"\n'
            'm_pValue = resource:"materials/models/weapons/customization/paints/x_pattern.vtex"\n'
        )
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertIn("x_pattern", found.path)

    def test_a_material_with_neither_texture_param_falls_back_to_none(self):
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertIsNone(found)

    def test_a_weapon_specific_vmat_variant_is_still_found(self):
        index = _fake_index([
            "materials/models/weapons/customization/paints/vmats/so_red_sg553.vmat_c",
        ])
        vmat_dump = ('m_name = "g_tPattern"\n'
                    'm_pValue = resource:"materials/.../so_red_sg553_pattern.vtex"\n')
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [], 0, stdout=vmat_dump.encode(), stderr=b"")):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_sg556", "so_red")
        self.assertIn("so_red_sg553_pattern", found.path)

    def test_a_skin_with_no_texture_anywhere_is_none_not_an_error(self):
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/unrelated.vmat_c"])
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "missing_kit")
        self.assertIsNone(found)

    def test_the_vmat_lookup_timing_out_is_treated_as_not_found(self):
        index = _fake_index(["materials/models/weapons/customization/paints/vmats/x.vmat_c"])
        with mock.patch.object(skin_render.vpk, "read_index", return_value=index), \
             mock.patch.object(skin_render.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("s2v", 30)):
            found = skin_render.texture_path(Path("d.vpk"), Path("s2v.exe"), "weapon_ak47", "x")
        self.assertIsNone(found)


class SerializingToolCalls(unittest.TestCase):
    """More than one invocation of the tool running at once made launches
    of it contend badly enough to look hung -- see _TOOL_LOCK's own
    comment. A render and a texture export (or two renders back to back)
    must never overlap."""

    def test_two_concurrent_renders_never_run_the_tool_at_the_same_time(self):
        overlap = threading.Event()
        active = {"n": 0}
        lock = threading.Lock()

        def fake_run(args, timeout=None, capture_output=None):
            with lock:
                active["n"] += 1
                if active["n"] > 1:
                    overlap.set()
            time.sleep(0.05)
            out_dir = Path(args[args.index("-o") + 1])
            (out_dir / "m.glb").write_bytes(b"x")
            with lock:
                active["n"] -= 1
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        def go():
            skin_render.render(Path("d.vpk"), "weapons/models/ak47/weapon_rif_ak47.vmdl",
                               Path("s2v.exe"))

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            threads = [threading.Thread(target=go) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertFalse(overlap.is_set())


class RenderingTheTexture(unittest.TestCase):
    def test_a_successful_export_returns_the_image_bytes(self):
        def fake_run(args, timeout=None, capture_output=None):
            out_dir = Path(args[args.index("-o") + 1])
            (out_dir / "tex.png").write_bytes(b"png-bytes")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            data = skin_render.render_texture(Path("d.vpk"), "materials/x.vtex", Path("s2v.exe"))
        self.assertEqual(data, b"png-bytes")

    def test_nothing_survives_after_the_call_returns(self):
        captured = {}

        def fake_run(args, timeout=None, capture_output=None):
            out_dir = Path(args[args.index("-o") + 1])
            captured["dir"] = out_dir
            (out_dir / "tex.png").write_bytes(b"x")
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            skin_render.render_texture(Path("d.vpk"), "materials/x.vtex", Path("s2v.exe"))
        self.assertFalse(captured["dir"].exists())

    def test_producing_nothing_is_a_render_error(self):
        def fake_run(args, timeout=None, capture_output=None):
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render_texture(Path("d.vpk"), "materials/x.vtex", Path("s2v.exe"))

    def test_a_nonzero_exit_is_a_render_error(self):
        def fake_run(args, timeout=None, capture_output=None):
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"bad path")

        with mock.patch.object(skin_render.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(skin_render.RenderError):
                skin_render.render_texture(Path("d.vpk"), "materials/x.vtex", Path("s2v.exe"))


if __name__ == "__main__":
    unittest.main()
