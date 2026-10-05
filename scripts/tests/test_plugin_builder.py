import json
import tempfile
import unittest
from pathlib import Path


from scripts.build_plugin import build_plugin


class PluginBuilderTest(unittest.TestCase):
    def test_builds_portable_manifest_and_copies_skill_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "skills" / "demo" / "scripts").mkdir(parents=True)
            (source / "skills" / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: Demo skill\n---\n\nUse demo.\n",
                encoding="utf-8",
            )
            (source / "skills" / "demo" / "scripts" / "run.sh").write_text(
                "#!/bin/sh\necho demo\n", encoding="utf-8"
            )
            output = root / "plugin"

            result = build_plugin(source, output, "demo-plugin", "1.2.3")

            self.assertEqual(result["name"], "demo-plugin")
            portable = json.loads((output / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(
                portable["$schema"],
                "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            )
            self.assertEqual(portable["name"], "demo-plugin")
            self.assertEqual((output / "skills/demo/scripts/run.sh").read_text(encoding="utf-8"),
                             "#!/bin/sh\necho demo\n")
            self.assertIn("description:", (output / "skills/demo/SKILL.md").read_text(encoding="utf-8"))
            codex = json.loads(
                (output / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual(codex["interface"]["displayName"], "Smooth")
            self.assertEqual(codex["skills"], "./skills/")
            kimi = json.loads((output / "kimi.plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(kimi["interface"]["displayName"], "Smooth")
            self.assertEqual(kimi["skills"], "./skills/")

    def test_dialectizes_manual_skill_for_opencode_and_kimi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "manual").mkdir(parents=True)
            (root / "skills" / "manual" / "SKILL.md").write_text(
                "---\nname: manual\n---\n\nManual workflow.\n", encoding="utf-8"
            )
            output = root / "plugin"

            build_plugin(root, output, "demo-plugin", "1.0.0")

            text = (output / "skills/manual/SKILL.md").read_text(encoding="utf-8")
            self.assertIn("disableModelInvocation: true", text)
            self.assertIn('opencode/autoinvoke: "false"', text)

    def test_build_rejects_plugin_name_that_is_not_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "demo").mkdir(parents=True)
            (root / "skills" / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: Demo\n---\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                build_plugin(root, root / "out", "Bad Name", "1.0.0")

            with self.assertRaises(ValueError):
                build_plugin(root, root / "out-period", "demo.plugin", "1.0.0")

    def test_build_rejects_skill_name_that_does_not_match_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "demo-skill").mkdir(parents=True)
            (root / "skills" / "demo-skill" / "SKILL.md").write_text(
                "---\nname: other-skill\ndescription: Demo\n---\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                build_plugin(root, root / "out", "demo-plugin", "1.0.0")

    def test_build_rejects_non_semver_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "demo").mkdir(parents=True)
            (root / "skills" / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: Demo\n---\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                build_plugin(root, root / "out", "demo-plugin", "local")
            with self.assertRaises(ValueError):
                build_plugin(root, root / "out-leading-zero", "demo-plugin", "01.2.3")


if __name__ == "__main__":
    unittest.main()
