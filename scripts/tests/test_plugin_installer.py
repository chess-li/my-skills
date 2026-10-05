import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


from scripts.plugin_installer import (
    _codex_root,
    _default_opencode_config,
    remove_kimi_personal_entry,
    remove_marketplace_entry,
    remove_opencode_config,
    uninstall,
    update_marketplace,
    update_opencode_config,
)


class PluginInstallerTest(unittest.TestCase):
    def test_marketplace_upsert_preserves_other_plugins_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marketplace = root / ".agents/plugins/marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "workspace-skills",
                        "plugins": [
                            {
                                "name": "other",
                                "source": {"source": "local", "path": "./other"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plugin = root / ".agents/plugins/demo"
            plugin.mkdir(parents=True)

            update_marketplace(marketplace, root, "demo", plugin)
            update_marketplace(marketplace, root, "demo", plugin)

            data = json.loads(marketplace.read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in data["plugins"]], ["other", "demo"])
            self.assertEqual(data["plugins"][-1]["source"]["path"], "./.agents/plugins/demo")

    def test_marketplace_removes_duplicate_entries_for_the_same_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marketplace = root / ".agents/plugins/marketplace.json"
            marketplace.parent.mkdir(parents=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "workspace-skills",
                        "plugins": [
                            {"name": "demo", "source": {"source": "local", "path": "./old"}},
                            {"name": "demo", "source": {"source": "local", "path": "./duplicate"}},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plugin = root / ".agents/plugins/demo"
            plugin.mkdir(parents=True)

            update_marketplace(marketplace, root, "demo", plugin)

            data = json.loads(marketplace.read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in data["plugins"]], ["demo"])
            self.assertEqual(data["plugins"][0]["source"]["path"], "./.agents/plugins/demo")

    def test_opencode_config_upsert_does_not_duplicate_plugin_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "opencode.json"
            config.write_text('{"$schema":"https://opencode.ai/config.json", "skills": []}', encoding="utf-8")
            skill_root = str((Path(tmp) / "plugin/skills").resolve())

            update_opencode_config(config, skill_root)
            update_opencode_config(config, skill_root)

            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data["skills"], [skill_root])

    def test_opencode_config_accepts_jsonc_and_prefers_existing_jsonc(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config/opencode"
            config_dir.mkdir(parents=True)
            config = config_dir / "opencode.jsonc"
            config.write_text(
                """{
                  // JSONC comments are accepted.
                  \"skills\": [\"/old\",],
                }\n""",
                encoding="utf-8",
            )
            skill_root = str((Path(tmp) / "plugin/skills").resolve())

            update_opencode_config(config, skill_root)

            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data["skills"], ["/old", skill_root])
            self.assertFalse((config_dir / "opencode.json").exists())

    def test_codex_root_follows_external_agents_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "external-home"
            plugin_store = root / ".agents/plugins"
            self.assertEqual(_codex_root(plugin_store), root.resolve())

    def test_cli_rejects_nonstandard_codex_marketplace_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            marketplace = home / ".agents/plugins/custom.json"
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--codex-marketplace",
                    str(marketplace),
                    "--skip-opencode",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["codex"])
            self.assertIn("marketplace.json", result["platforms"]["codex"]["error"])

    def test_cli_rejects_nested_codex_marketplace_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            marketplace = home / ".agents/plugins/nested/marketplace.json"
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--codex-marketplace",
                    str(marketplace),
                    "--skip-opencode",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["codex"])
            self.assertIn("plugin store", result["platforms"]["codex"]["error"])

    def test_default_opencode_config_detects_existing_jsonc(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config = home / ".config/opencode/opencode.jsonc"
            config.parent.mkdir(parents=True)
            config.write_text("{}", encoding="utf-8")
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(_default_opencode_config(home), config)

    def test_cli_installs_a_plugin_without_creating_a_scattered_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config = root / "opencode.json"
            store = home / ".agents/plugins"
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(store),
                    "--opencode-config",
                    str(config),
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((store / "smooth/plugin.json").is_file())
            self.assertFalse((home / ".agents/skills").exists())

    def test_platform_failure_is_reported_after_other_platforms_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config = root / "opencode.json"
            failing_register = root / "register-fails.py"
            failing_register.write_text(
                "import sys\nsys.exit('simulated Kimi failure')\n", encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--opencode-config",
                    str(config),
                    "--skip-codex",
                    "--kimi-register",
                    str(failing_register),
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["kimi-work"])
            self.assertTrue(config.is_file())
            self.assertTrue((home / ".agents/plugins/smooth/plugin.json").is_file())

    def test_remove_opencode_config_keeps_other_skill_roots_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "opencode.json"
            keep = str((Path(tmp) / "keep/skills").resolve())
            remove = str((Path(tmp) / "smooth/skills").resolve())
            config.write_text(json.dumps({"skills": [keep, remove, remove]}), encoding="utf-8")

            first = remove_opencode_config(config, remove)
            second = remove_opencode_config(config, remove)

            self.assertEqual(first["removed"], 2)
            self.assertEqual(second["removed"], 0)
            self.assertEqual(json.loads(config.read_text())["skills"], [keep])

    def test_remove_marketplace_entry_matches_name_and_source_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marketplace = root / ".agents/plugins/marketplace.json"
            marketplace.parent.mkdir(parents=True)
            plugin = root / ".agents/plugins/smooth"
            plugin.mkdir(parents=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "workspace-skills",
                        "plugins": [
                            {"name": "smooth", "source": {"source": "local", "path": "./.agents/plugins/smooth"}},
                            {"name": "other", "source": {"source": "local", "path": "./other"}},
                            {"name": "smooth", "source": {"source": "local", "path": "./other-smooth"}},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            first = remove_marketplace_entry(marketplace, root, "smooth", plugin)
            second = remove_marketplace_entry(marketplace, root, "smooth", plugin)

            self.assertEqual(first["removed"], 1)
            self.assertEqual(second["removed"], 0)
            data = json.loads(marketplace.read_text())
            self.assertEqual([item["name"] for item in data["plugins"]], ["other", "smooth"])

    def test_uninstall_keeps_source_when_codex_cli_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            plugin_store = home / ".agents/plugins"
            plugin = plugin_store / "smooth"
            plugin.mkdir(parents=True)
            marketplace = plugin_store / "marketplace.json"
            marketplace.parent.mkdir(parents=True, exist_ok=True)
            marketplace.write_text(
                json.dumps(
                    {
                        "name": "workspace-skills",
                        "plugins": [
                            {
                                "name": "smooth",
                                "source": {"source": "local", "path": "./.agents/plugins/smooth"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            cache = home / ".codex/plugins/cache/workspace-skills/smooth/1.0.0"
            cache.mkdir(parents=True)
            (cache / "plugin.json").write_text("{}", encoding="utf-8")
            args = type("Args", (), {
                "name": "smooth",
                "home": home,
                "plugin_store": plugin_store,
                "codex_marketplace": None,
                "opencode_config": None,
                "kimi_share_dir": None,
                "skip_opencode": True,
                "skip_codex": False,
                "skip_kimi": True,
            })()

            with patch("scripts.plugin_installer.shutil.which", return_value=None):
                result = uninstall(args)

            self.assertEqual(result["failures"], ["codex"])
            self.assertTrue(plugin.exists())
            self.assertTrue(cache.exists())
            self.assertEqual(len(json.loads(marketplace.read_text())["plugins"]), 1)

    def test_uninstall_requires_kimi_share_dir_to_remove_kimi_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            plugin_store = home / ".agents/plugins"
            plugin = plugin_store / "smooth"
            plugin.mkdir(parents=True)
            args = type("Args", (), {
                "name": "smooth",
                "home": home,
                "plugin_store": plugin_store,
                "codex_marketplace": None,
                "opencode_config": None,
                "kimi_share_dir": None,
                "skip_opencode": True,
                "skip_codex": True,
                "skip_kimi": False,
            })()

            result = uninstall(args)

            self.assertEqual(result["failures"], ["kimi-work"])
            self.assertTrue(plugin.exists())

    def test_remove_kimi_entry_requires_matching_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            share = root / "share"
            market = share / "daimon/plugin-market/personal"
            market.mkdir(parents=True)
            plugin = root / ".agents/plugins/smooth"
            plugin.mkdir(parents=True)
            entry = market / "smooth.json"
            entry.write_text(
                json.dumps({"id": "smooth", "sourcePath": str(plugin)}), encoding="utf-8"
            )

            first = remove_kimi_personal_entry(share, "smooth", plugin)
            second = remove_kimi_personal_entry(share, "smooth", plugin)

            self.assertTrue(first["removed"])
            self.assertFalse(second["removed"])
            self.assertFalse(entry.exists())

    def test_cli_uninstall_removes_source_and_opencode_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config = root / "opencode.json"
            install = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--opencode-config",
                    str(config),
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, install.stderr)

            first = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--opencode-config",
                    str(config),
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--opencode-config",
                    str(config),
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse((home / ".agents/plugins/smooth").exists())
            self.assertEqual(json.loads(config.read_text())["skills"], [])
            self.assertEqual(json.loads(first.stdout)["failures"], [])
            self.assertEqual(json.loads(second.stdout)["failures"], [])

    def test_missing_kimi_client_is_reported_without_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(root / "home"),
                    "--plugin-store",
                    str(root / "home/.agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], [])
            self.assertFalse(result["platforms"]["kimi-work"]["registered"])


if __name__ == "__main__":
    unittest.main()
