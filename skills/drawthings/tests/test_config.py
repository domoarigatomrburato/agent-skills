import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from drawthings_py import Configs
from PIL import Image


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dt_render = load_module("dt_render", SKILL / "scripts" / "dt_render.py")
png_config = load_module("png_config", SKILL / "scripts" / "png_config.py")


class ConfigurationRecipeTests(unittest.TestCase):
    def test_false_zero_empty_and_enums_survive_sdk_mapping(self):
        config = dt_render.config_dict_from_app({
            "model": "qwen_image_2512_q8p.ckpt",
            "resolutionDependentShift": False,
            "maskBlurOutset": 0,
            "hiresFix": False,
            "sampler": 15,
            "seedMode": 2,
            "loras": [],
        })
        self.assertIs(config["resolution_dependent_shift"], False)
        self.assertEqual(config["mask_blur_outset"], 0)
        self.assertIs(config["hires_fix"], False)
        self.assertEqual(config["sampler"], "DPMPP2MTrailing")
        self.assertEqual(config["seed_mode"], "ScaleAlike")
        self.assertEqual(config["loras"], [])
        sent = Configs.create(config)
        received = Configs.create().from_fbs(sent.to_fbs())
        self.assertIs(received._d["resolution_dependent_shift"], False)
        self.assertEqual(received._d["mask_blur_outset"], 0)

    def test_recipe_wrapper_and_bare_configuration_are_accepted(self):
        bare = {"model": "qwen_image_2512_q8p.ckpt", "steps": 36}
        for document, prompt in ((bare, None), ({
            "name": "qwen",
            "prompt": "observer",
            "negative": "",
            "configuration": bare,
        }, "observer")):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                loaded = dt_render.load_config_recipe(str(path))
            self.assertEqual(loaded["sdk"]["model"], bare["model"])
            self.assertEqual(loaded["sdk"]["steps"], 36)
            self.assertEqual(loaded["prompt"], prompt)

    def test_export_preserves_unknown_app_fields_and_updates_seed(self):
        raw = {"colorCalibration": "none", "resolutionDependentShift": False}
        effective = {
            "model": "qwen_image_2512_q8p.ckpt", "width": 1920, "height": 1280,
            "steps": 36, "guidance": 4.0, "strength": 1.0, "sampler": "DPMPP2MTrailing",
            "shift": 3.99, "resolution_dependent_shift": False, "batch_count": 1,
            "batch_size": 1, "seed_mode": "ScaleAlike", "tiled_decoding": False,
            "zero_negative_prompt": False, "loras": [], "controls": [],
        }
        exported = dt_render.app_configuration(raw, effective, 3160419753)
        self.assertEqual(exported["colorCalibration"], "none")
        self.assertEqual(exported["seed"], 3160419753)
        self.assertEqual(exported["sampler"], 15)
        self.assertIs(exported["resolutionDependentShift"], False)

    def test_png_v2_is_the_configuration_block(self):
        v2 = {"model": "model.ckpt", "seed": 42}
        self.assertIs(png_config.configuration_block({"v2": v2}), v2)

    def test_init_image_fill_covers_canvas_with_center_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wide.png"
            Image.new("RGB", (400, 200), (10, 20, 30)).save(source)
            prepared, metadata = dt_render.prepare_init_image(str(source), 300, 300, "fill")
        self.assertEqual((prepared.width, prepared.height, prepared.channels), (300, 300, 3))
        self.assertEqual(metadata["source_size"], [400, 200])
        self.assertEqual(metadata["resized_size"], [600, 300])
        self.assertEqual(metadata["crop"], [150, 0, 450, 300])

    def test_config_recipe_resolves_saved_init_image_relative_to_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "init-image.png").write_bytes(b"placeholder")
            config = root / "result.config.json"
            config.write_text(json.dumps({
                "name": "upscale", "prompt": "", "negative": "",
                "init_image": "init-image.png", "init_fit": "fill",
                "configuration": {"model": "seedvr2_7b_q8p.ckpt"},
            }), encoding="utf-8")
            loaded = dt_render.load_config_recipe(str(config))
        self.assertEqual(loaded["init_image"], str((root / "init-image.png").resolve()))
        self.assertEqual(loaded["init_fit"], "fill")

    def test_tiled_decode_turns_on_above_the_recipe_threshold(self):
        defaults = {"tiled_decode_above": 2_800_000}
        with redirect_stdout(io.StringIO()):
            self.assertTrue(dt_render.auto_tiled_decode(None, False, defaults, 1600, 2048))
        self.assertFalse(dt_render.auto_tiled_decode(None, False, defaults, 2048, 1344))
        self.assertFalse(dt_render.auto_tiled_decode(False, False, defaults, 1600, 2048))  # --no-tiled-decode wins
        self.assertFalse(dt_render.auto_tiled_decode(None, False, {}, 1600, 2048))  # recipes without the key
        self.assertTrue(dt_render.auto_tiled_decode(True, True, defaults, 1024, 1024))

    def test_strength_flag_overrides_cloud_upscale_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (64, 64), (128, 128, 128)).save(source)
            config = root / "config.json"
            config.write_text(json.dumps({
                "configuration": {"model": "seedvr2_7b_q8p.ckpt", "strength": 1.0, "seed": 42},
            }), encoding="utf-8")
            argv = ["dt_render.py", "--config", str(config), "--init-image", str(source),
                    "--strength", "0.8", "--estimate-only"]
            output = io.StringIO()
            with patch("sys.argv", argv), redirect_stdout(output):
                self.assertEqual(dt_render.main(), 0)
            self.assertIn("strength 0.8", output.getvalue())


if __name__ == "__main__":
    unittest.main()
