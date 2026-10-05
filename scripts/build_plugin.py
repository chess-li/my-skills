#!/usr/bin/env python3
"""Build the repository skills as one portable Agent Plugin.

The repository remains the source of truth.  This command creates a self-contained
copy so each client can install one plugin directory without following paths outside
the package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


PORTABLE_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
KIMI_SCHEMA = "https://catalog.msh.team/schemas/kimi.plugin.schema.json"
DEFAULT_DESCRIPTION = "Portable SDD skills for OpenCode, Codex, and Kimi Work."
# Kimi Work uses the stricter kebab-case form.  Using the intersection here
# keeps one generated package valid for all three harnesses.
PLUGIN_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
MARKDOWN_LINK_RE = re.compile(r"(\[[^\]]*\]\()([^)\s]+)(\))")
VERSION_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def validate_plugin_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 64
        or not PLUGIN_NAME_RE.fullmatch(name)
        or "--" in name
        or ".." in name
    ):
        raise ValueError(
            "plugin name must be 1-64 lowercase ASCII letters, digits, or hyphens; "
            "it cannot start/end with punctuation or contain --"
        )
    return name


def _frontmatter(skill_file: Path) -> dict[str, str]:
    """Read the small scalar subset needed for platform presentation fields."""
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.strip().strip("\"'")
        if key.strip() in {"name", "description"} and value:
            fields[key.strip()] = value
    return fields


def _assert_no_symlinks(path: Path) -> None:
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"plugin source contains a symlink: {item}")


def _skill_dirs(skill_root: Path) -> list[Path]:
    """Find skill directories at skills/<name> or skills/<scene>/<name>."""
    found: list[Path] = []
    seen: dict[str, Path] = {}

    def add(skill_dir: Path) -> None:
        previous = seen.get(skill_dir.name)
        if previous is not None:
            raise ValueError(
                f"duplicate skill name {skill_dir.name!r}: {previous} and {skill_dir}"
            )
        seen[skill_dir.name] = skill_dir
        found.append(skill_dir)

    for child in sorted(path for path in skill_root.iterdir() if path.is_dir()):
        if (child / "SKILL.md").is_file():
            add(child)
            continue
        for nested in sorted(path for path in child.iterdir() if path.is_dir()):
            if (nested / "SKILL.md").is_file():
                add(nested)
    return found


def _locate_in_skill(path: Path, skill_dirs: list[Path]) -> tuple[str, Path] | None:
    resolved = path.resolve()
    matches: list[tuple[int, str, Path]] = []
    for skill_dir in skill_dirs:
        try:
            relative = resolved.relative_to(skill_dir.resolve())
        except ValueError:
            continue
        matches.append((len(skill_dir.parts), skill_dir.name, relative))
    if not matches:
        return None
    _, name, relative = max(matches)
    return name, relative


def _rewrite_skill_links(
    dest_file: Path,
    source_file: Path,
    skill_dirs: list[Path],
    output_skills: Path,
) -> None:
    """Point copied cross-skill links at the flat package, not the scene tree."""
    text = dest_file.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        target = match.group(2)
        if target.startswith(("#", "http://", "https://", "mailto:")):
            return match.group(0)
        raw, separator, anchor = target.partition("#")
        if not raw.startswith("."):
            return match.group(0)
        resolved = (source_file.parent / raw).resolve()
        if not resolved.is_file():
            return match.group(0)
        located = _locate_in_skill(resolved, skill_dirs)
        if located is None:
            return match.group(0)
        name, relative = located
        dest_target = (output_skills / name / relative).resolve()
        if not dest_target.is_relative_to(output_skills.resolve()):
            raise ValueError(f"skill link escapes the package: {target}")
        rewritten = Path(os.path.relpath(dest_target, dest_file.parent.resolve())).as_posix()
        if not rewritten.startswith("."):
            rewritten = "./" + rewritten
        suffix = f"#{anchor}" if separator else ""
        return f"{match.group(1)}{rewritten}{suffix}{match.group(3)}"

    updated = MARKDOWN_LINK_RE.sub(replace, text)
    if updated != text:
        dest_file.write_text(updated, encoding="utf-8")


def _skill_metadata(skill_dirs: list[Path]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for skill_dir in skill_dirs:
        if not SKILL_NAME_RE.fullmatch(skill_dir.name) or "--" in skill_dir.name:
            raise ValueError(
                f"skill directory must use lowercase kebab-case: {skill_dir.name}"
            )
        metadata = _frontmatter(skill_dir / "SKILL.md")
        name = metadata.get("name")
        if name != skill_dir.name:
            raise ValueError(
                f"skill frontmatter name must match its directory: "
                f"{skill_dir.name!r} != {name!r}"
            )
        description = metadata.get("description", f"Use the {name} skill.")
        result.append({"name": name, "description": description})
    return result


def _dialectize_skill(skill_file: Path) -> None:
    """Give legacy user-invoked skills valid Agent Skills metadata.

    A few repository skills intentionally omit ``description`` so they are only
    invoked by a person.  Portable clients require the field.  The generated
    copy keeps that intent with OpenCode's explicit auto-invocation switch.
    """
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return
    end = text.find("\n---", 4)
    if end < 0 or re.search(r"^description:\s*\S", text[4:end], re.MULTILINE):
        return
    header = text[4:end].splitlines()
    name = next((line.split(":", 1)[1].strip() for line in header if line.startswith("name:")), skill_file.parent.name)
    header.append(f"description: Use the {name} skill when the user explicitly requests its workflow.")
    # Kimi Work uses this field to preserve the manual-only behavior of the
    # repository skills that intentionally omit a description.
    header.append("disableModelInvocation: true")
    if any(line.strip() == "metadata:" for line in header):
        header.append('  opencode/autoinvoke: "false"')
    else:
        header.append("metadata:")
        header.append('  opencode/autoinvoke: "false"')
    body = text[end + 4 :]
    skill_file.write_text("---\n" + "\n".join(header) + "\n---" + body, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_plugin(
    source_root: Path,
    output_dir: Path,
    plugin_name: str,
    version: str,
    description: str = DEFAULT_DESCRIPTION,
) -> dict[str, Any]:
    """Create a portable package and return its summary.

    ``source_root`` must contain a ``skills`` directory.  ``output_dir`` must not
    already exist.  The explicit refusal prevents an update from accidentally
    deleting user-authored files in a plugin source directory.
    """
    source_root = Path(source_root).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    validate_plugin_name(plugin_name)
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version.strip()):
        raise ValueError("plugin version must be semantic version x.y.z (optional prerelease/build metadata)")
    skill_source = source_root / "skills"
    if not skill_source.is_dir():
        raise ValueError(f"skills directory not found: {skill_source}")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    # Only files copied into the package need the containment check.  The
    # repository may contain unrelated development symlinks in node_modules.
    _assert_no_symlinks(skill_source)
    skill_dirs = _skill_dirs(skill_source)
    metadata = _skill_metadata(skill_dirs)
    if not metadata:
        raise ValueError("no skills/<name>/SKILL.md or skills/<scene>/<name>/SKILL.md files found")

    output_dir.mkdir(parents=True)
    target_skills = output_dir / "skills"
    target_skills.mkdir()
    for item in skill_dirs:
        destination = target_skills / item.name
        shutil.copytree(
            item,
            destination,
            symlinks=False,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"),
        )
        for copied in destination.rglob("*.md"):
            if copied.is_file():
                _rewrite_skill_links(copied, item / copied.relative_to(destination), skill_dirs, target_skills)
        _dialectize_skill(destination / "SKILL.md")

    portable = {
        "$schema": PORTABLE_SCHEMA,
        "name": plugin_name,
        "version": version,
        "description": description,
        "keywords": ["agent-skills", "sdd", "spec-driven-development"],
    }
    _write_json(output_dir / "plugin.json", portable)

    display_name = "Smooth"
    _write_json(
        output_dir / ".codex-plugin" / "plugin.json",
        {
            "name": plugin_name,
            "version": version,
            "description": description,
            "skills": "./skills/",
            "interface": {
                "displayName": display_name,
                "shortDescription": "Spec-driven development workflows",
            },
        },
    )

    skill_overrides = {
        item["name"]: {
            "displayName": item["name"].replace("-", " ").title(),
            "description": item["description"],
        }
        for item in metadata
    }
    _write_json(
        output_dir / "kimi.plugin.json",
        {
            "$schema": KIMI_SCHEMA,
            "name": plugin_name,
            "version": version,
            "description": description,
            "keywords": ["agent skills", "SDD", "spec-driven development"],
            "author": "Local developer",
            "license": "UNLICENSED",
            "skills": "./skills/",
            "skillInstructions": (
                "Load the skill that matches the user's request. Keep the skill's "
                "workflow and referenced files together inside this plugin."
            ),
            "interface": {
                "displayName": display_name,
                "shortDescription": "Spec-driven development workflows",
                "longDescription": description,
                "developerName": "Local developer",
                "category": "PRODUCTIVITY",
                "defaultLocale": "zh-CN",
                "locales": "./locales/",
                "tryPrompts": ["帮我选择并执行合适的规格驱动开发 workflow"],
                "skillOverrides": skill_overrides,
            },
        },
    )
    locale_base = {
        "displayName": display_name,
        "shortDescription": "Spec-driven development workflows",
        "longDescription": description,
        "developerName": "Local developer",
        "tryPrompts": ["Help me choose and run the right spec-driven workflow"],
        "skillOverrides": skill_overrides,
    }
    _write_json(output_dir / "locales" / "zh-CN.json", {
        **locale_base,
        "shortDescription": "规格驱动开发工作流",
        "longDescription": "提供规格驱动开发所需的工作流。",
        "tryPrompts": ["帮我选择并执行合适的规格驱动开发工作流"],
    })
    _write_json(output_dir / "locales" / "en-US.json", locale_base)

    return {
        "name": plugin_name,
        "version": version,
        "output": str(output_dir),
        "skills": [item["name"] for item in metadata],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--name", default="smooth")
    parser.add_argument("--version", required=True)
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = build_plugin(
        args.source_root,
        args.output_dir,
        args.name,
        args.version,
        args.description,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
