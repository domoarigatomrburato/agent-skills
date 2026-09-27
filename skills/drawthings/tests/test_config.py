import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from drawthings_py import Configs


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


if __name__ == "__main__":
    unittest.main()
