import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
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
                    "--skip-gemini",
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
                    "--skip-gemini",
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
                    "--skip-gemini",
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
                    "--skip-gemini",
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
                "skip_gemini": True,
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
                "skip_gemini": True,
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
                    "--skip-gemini",
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
                    "--skip-gemini",
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
                    "--skip-gemini",
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

    def test_cli_installs_gemini_copy_through_agy_in_the_specified_home(self):
        real_plugins = Path.home() / ".gemini/config/plugins"
        before = real_plugins.stat().st_mtime_ns if real_plugins.exists() else None
        real_agy = shutil.which("agy")
        self.assertIsNotNone(real_agy)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$HOME\" >> {log}\n"
                f"printf '%s\\n' \"$@\" >> {log}\n"
                f"exec {real_agy} \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
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
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            copy = home / ".gemini/config/plugins/smooth"
            self.assertTrue((copy / "plugin.json").is_file())
            self.assertTrue((copy / "skills").is_dir())
            self.assertFalse((copy / "gemini-extension.json").exists())
            self.assertFalse((home / ".agents/plugins/smooth/gemini-extension.json").exists())
            self.assertFalse((home / ".gemini/config/skills").exists())
            manifest = json.loads((home / ".gemini/config/import_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in manifest["imports"]], ["smooth"])
            recorded = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(recorded[0], str(home.resolve()))
            self.assertEqual(recorded[1:3], ["plugin", "install"])
            self.assertEqual(Path(recorded[3]), (home / ".agents/plugins/smooth").resolve())
        after = real_plugins.stat().st_mtime_ns if real_plugins.exists() else None
        self.assertEqual(before, after)

    def test_cli_uninstalls_gemini_copy_and_keeps_another_plugin(self):
        real_agy = shutil.which("agy")
        self.assertIsNotNone(real_agy)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            other = root / "other"
            other.mkdir()
            (other / "plugin.json").write_text('{"name": "other"}\n', encoding="utf-8")
            (other / "skills").mkdir()
            installed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr + installed.stdout)
            other_install = subprocess.run(
                [real_agy, "plugin", "install", str(other)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home)},
            )
            self.assertEqual(other_install.returncode, 0, other_install.stderr)
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" >> {log}\n"
                f"exec {real_agy} \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            first = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["plugin", "uninstall", "smooth"],
            )
            self.assertFalse((home / ".gemini/config/plugins/smooth").exists())
            self.assertTrue((home / ".gemini/config/plugins/other/plugin.json").is_file())
            manifest = json.loads(
                (home / ".gemini/config/import_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual([item["name"] for item in manifest["imports"]], ["other"])
            self.assertFalse((home / ".agents/plugins/smooth").exists())

    def test_gemini_uninstall_keeps_same_name_directory_with_a_different_manifest_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            copy = home / ".gemini/config/plugins/smooth"
            copy.mkdir(parents=True)
            (copy / "plugin.json").write_text('{"name": "not-ours"}\n', encoding="utf-8")
            (copy / "keep.txt").write_text("foreign\n", encoding="utf-8")
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" >> {log}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["gemini"])
            self.assertEqual((copy / "plugin.json").read_text(encoding="utf-8"), '{"name": "not-ours"}\n')
            self.assertEqual((copy / "keep.txt").read_text(encoding="utf-8"), "foreign\n")
            self.assertTrue(source.is_dir())
            self.assertFalse(log.exists())

    def test_gemini_uninstall_keeps_directory_without_a_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            copy = home / ".gemini/config/plugins/smooth"
            copy.mkdir(parents=True)
            (copy / "keep.txt").write_text("no-manifest\n", encoding="utf-8")
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' called >> {log}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertEqual(json.loads(completed.stdout)["failures"], ["gemini"])
            self.assertEqual((copy / "keep.txt").read_text(encoding="utf-8"), "no-manifest\n")
            self.assertTrue(source.is_dir())
            self.assertFalse(log.exists())

    def test_gemini_uninstall_keeps_directory_with_invalid_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            copy = home / ".gemini/config/plugins/smooth"
            copy.mkdir(parents=True)
            (copy / "plugin.json").write_text("{", encoding="utf-8")
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' called >> {log}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertIn("not valid JSON", json.loads(completed.stdout)["platforms"]["gemini"]["error"])
            self.assertEqual((copy / "plugin.json").read_text(encoding="utf-8"), "{")
            self.assertTrue(source.is_dir())
            self.assertFalse(log.exists())

    def test_gemini_uninstall_without_agy_keeps_existing_copy_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            copy = home / ".gemini/config/plugins/smooth"
            copy.mkdir(parents=True)
            (copy / "plugin.json").write_text('{"name": "smooth"}\n', encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = "/usr/bin:/bin"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["gemini"])
            self.assertIn("agy executable not found", result["platforms"]["gemini"]["error"])
            self.assertEqual((copy / "plugin.json").read_text(encoding="utf-8"), '{"name": "smooth"}\n')
            self.assertTrue(source.is_dir())

    def test_install_sh_skips_gemini_when_disabled_and_invokes_agy_by_default(self):
        real_agy = shutil.which("agy")
        self.assertIsNotNone(real_agy)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            log = root / "agy.log"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" >> {log}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["HOME"] = str(home)
            env["INSTALL_OPENCODE"] = "0"
            env["INSTALL_CODEX"] = "0"
            env["INSTALL_KIMI_WORK"] = "0"
            env["INSTALL_GEMINI"] = "0"
            skipped = subprocess.run(
                ["bash", "scripts/install.sh"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(skipped.returncode, 0, skipped.stderr + skipped.stdout)
            self.assertFalse(log.exists())
            self.assertFalse((home / ".gemini").exists())

            env["INSTALL_GEMINI"] = "1"
            enabled = subprocess.run(
                ["bash", "scripts/install.sh"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(enabled.returncode, 0, enabled.stderr + enabled.stdout)
            recorded = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(recorded[:2], ["plugin", "install"])
            self.assertEqual(Path(recorded[2]), (home / ".agents/plugins/smooth").resolve())

            env["INSTALL_GEMINI"] = "0"
            removed = subprocess.run(
                ["bash", "scripts/uninstall.sh"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(removed.returncode, 0, removed.stderr + removed.stdout)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), recorded)

    def test_missing_agy_reports_gemini_failure_without_writing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config = root / "opencode.json"
            env = os.environ.copy()
            env["PATH"] = "/usr/bin:/bin"
            completed = subprocess.run(
                [
                    sys.executable,
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
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["failures"], ["gemini"])
            self.assertIn("agy executable not found", result["platforms"]["gemini"]["error"])
            self.assertTrue(config.is_file())
            self.assertIn("smooth/skills", json.loads(config.read_text(encoding="utf-8"))["skills"][0])
            self.assertFalse((home / ".gemini").exists())

    def test_failing_agy_install_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            count = root / "count"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf 'x' >> {count}\n"
                "exit 1\n",
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertEqual(count.read_text(encoding="utf-8"), "x")
            self.assertEqual(json.loads(completed.stdout)["failures"], ["gemini"])
            self.assertFalse((home / ".gemini").exists())

    def test_gemini_install_waits_until_agy_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            wrapper = bin_dir / "agy"
            wrapper.write_text("#!/bin/sh\nsleep 0.4\nexit 0\n", encoding="utf-8")
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            started = time.monotonic()
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/plugin_installer.py",
                    "--source-root",
                    ".",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                    "--version",
                    "1.0.0",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertGreaterEqual(elapsed, 0.4)

    def test_repeat_gemini_install_overwrites_copy_and_keeps_other_plugin(self):
        real_agy = shutil.which("agy")
        self.assertIsNotNone(real_agy)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            store = home / ".agents/plugins"
            command = [
                sys.executable,
                "scripts/plugin_installer.py",
                "--source-root",
                ".",
                "--home",
                str(home),
                "--plugin-store",
                str(store),
                "--skip-opencode",
                "--skip-codex",
                "--skip-kimi",
                "--version",
                "1.0.0",
            ]
            first = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            copy = home / ".gemini/config/plugins/smooth"
            (copy / "marker.txt").write_text("stale\n", encoding="utf-8")
            other = root / "other"
            (other / "skills").mkdir(parents=True)
            (other / "plugin.json").write_text('{"name": "other"}\n', encoding="utf-8")
            other_install = subprocess.run(
                [real_agy, "plugin", "install", str(other)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home)},
            )
            self.assertEqual(other_install.returncode, 0, other_install.stderr)
            second = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertFalse((copy / "marker.txt").exists())
            self.assertTrue((copy / "plugin.json").is_file())
            self.assertTrue((home / ".gemini/config/plugins/other/plugin.json").is_file())
            manifest = json.loads((home / ".gemini/config/import_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in manifest["imports"]], ["smooth", "other"])

    def test_gemini_uninstall_without_agy_keeps_import_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            manifest = home / ".gemini/config/import_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps({"imports": [{"name": "smooth", "source": "antigravity"}, {"name": "other"}]}),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PATH"] = "/usr/bin:/bin"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertEqual(json.loads(completed.stdout)["failures"], ["gemini"])
            self.assertEqual(
                json.loads(manifest.read_text(encoding="utf-8"))["imports"],
                [{"name": "smooth", "source": "antigravity"}, {"name": "other"}],
            )
            self.assertTrue(source.is_dir())

    def test_gemini_uninstall_without_agy_succeeds_when_nothing_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            source = home / ".agents/plugins/smooth"
            source.mkdir(parents=True)
            env = os.environ.copy()
            env["PATH"] = "/usr/bin:/bin"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/plugin_installer.py",
                    "--uninstall",
                    "--home",
                    str(home),
                    "--plugin-store",
                    str(home / ".agents/plugins"),
                    "--skip-opencode",
                    "--skip-codex",
                    "--skip-kimi",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["failures"], [])
            self.assertFalse(source.exists())
            self.assertFalse((home / ".gemini").exists())

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
                    "--skip-gemini",
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
