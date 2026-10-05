#!/usr/bin/env python3
"""Install or uninstall one generated plugin through native client entry points."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:  # package import in tests; direct import when called as a script
    from .build_plugin import build_plugin, validate_plugin_name
except ImportError:  # pragma: no cover - exercised by the CLI entry point
    from build_plugin import build_plugin, validate_plugin_name


MARKETPLACE_NAME = "workspace-skills"
DEFAULT_PLUGIN_NAME = "smooth"


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _strip_jsonc(text: str) -> str:
    """Remove JSONC comments and trailing commas without touching strings."""
    without_comments: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            without_comments.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            without_comments.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "*":
            index += 2
            while index + 1 < len(text) and text[index:index + 2] != "*/":
                if text[index] in "\r\n":
                    without_comments.append(text[index])
                else:
                    without_comments.append(" ")
                index += 1
            if index + 1 >= len(text):
                raise ValueError("unterminated JSONC block comment")
            index += 2
            continue
        without_comments.append(char)
        index += 1

    cleaned: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(without_comments):
        char = without_comments[index]
        if in_string:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(without_comments) and without_comments[lookahead].isspace():
                lookahead += 1
            if lookahead < len(without_comments) and without_comments[lookahead] in "]}":
                index += 1
                continue
        cleaned.append(char)
        index += 1
    return "".join(cleaned)


def _read_jsonc(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        value = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSONC: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSONC root must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def update_marketplace(
    marketplace_file: Path,
    marketplace_root: Path,
    plugin_name: str,
    plugin_dir: Path,
    display_name: str = "Workspace Skills",
) -> dict[str, Any]:
    """Upsert a local Codex marketplace entry without touching other entries."""
    marketplace_file = Path(marketplace_file).expanduser().resolve()
    marketplace_root = Path(marketplace_root).expanduser().resolve()
    plugin_dir = Path(plugin_dir).expanduser().resolve()
    try:
        relative = plugin_dir.relative_to(marketplace_root)
    except ValueError as exc:
        raise ValueError("Codex plugin source must be inside the marketplace root") from exc
    source_path = "./" + relative.as_posix()
    data = _read_json(
        marketplace_file,
        {
            "name": MARKETPLACE_NAME,
            "interface": {"displayName": display_name},
            "plugins": [],
        },
    )
    data.setdefault("name", MARKETPLACE_NAME)
    if not isinstance(data.get("interface"), dict):
        data["interface"] = {}
    data["interface"].setdefault("displayName", display_name)
    if not isinstance(data.get("plugins"), list):
        raise ValueError(f"marketplace plugins must be an array: {marketplace_file}")
    entry = {
        "name": plugin_name,
        "source": {"source": "local", "path": source_path},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }
    replaced = False
    plugins: list[Any] = []
    for existing in data["plugins"]:
        if isinstance(existing, dict) and existing.get("name") == plugin_name:
            if not replaced:
                plugins.append(entry)
                replaced = True
            continue
        plugins.append(existing)
    if not replaced:
        plugins.append(entry)
    data["plugins"] = plugins
    _write_json(marketplace_file, data)
    return {
        "path": str(marketplace_file),
        "marketplaceName": data["name"],
        "plugin": entry,
        "replaced": replaced,
    }


def _marketplace_source_path(entry: Any, marketplace_root: Path) -> Path | None:
    if not isinstance(entry, dict):
        return None
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "local":
        return None
    source_value = source.get("path")
    if not isinstance(source_value, str) or not source_value:
        return None
    source_path = Path(source_value).expanduser()
    if not source_path.is_absolute():
        source_path = marketplace_root / source_path
    return source_path.resolve()


def remove_marketplace_entry(
    marketplace_file: Path,
    marketplace_root: Path,
    plugin_name: str,
    plugin_dir: Path,
) -> dict[str, Any]:
    """Remove only the entry whose name and local source both match this plugin."""
    marketplace_file = Path(marketplace_file).expanduser().resolve()
    marketplace_root = Path(marketplace_root).expanduser().resolve()
    plugin_dir = Path(plugin_dir).expanduser().resolve()
    if not marketplace_file.exists():
        return {"path": str(marketplace_file), "removed": 0, "skipped": "marketplace not found"}
    data = _read_json(marketplace_file, {})
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError(f"marketplace plugins must be an array: {marketplace_file}")
    kept = []
    for item in plugins:
        matches = (
            isinstance(item, dict)
            and item.get("name") == plugin_name
            and _marketplace_source_path(item, marketplace_root) == plugin_dir
        )
        if not matches:
            kept.append(item)
    removed = len(plugins) - len(kept)
    if removed:
        data["plugins"] = kept
        _write_json(marketplace_file, data)
    return {"path": str(marketplace_file), "removed": removed}


def update_opencode_config(config_file: Path, skill_root: str) -> dict[str, Any]:
    """Add one plugin skill root to OpenCode's native skills source list."""
    config_file = Path(config_file).expanduser().resolve()
    skill_root = str(Path(skill_root).expanduser().resolve())
    data = _read_jsonc(config_file, {"$schema": "https://opencode.ai/config.json"})
    current = data.get("skills", [])
    if isinstance(current, str):
        current = [current]
    if not isinstance(current, list) or any(not isinstance(item, str) for item in current):
        raise ValueError(f"OpenCode skills must be a string array: {config_file}")
    current = [item for item in current if item != skill_root]
    current.append(skill_root)
    data["skills"] = current
    _write_json(config_file, data)
    return {"path": str(config_file), "skillRoot": skill_root, "count": len(current)}


def remove_opencode_config(config_file: Path, skill_root: str) -> dict[str, Any]:
    """Remove only this plugin's exact skills source from OpenCode config."""
    config_file = Path(config_file).expanduser().resolve()
    skill_root = str(Path(skill_root).expanduser().resolve())
    if not config_file.exists():
        return {"path": str(config_file), "removed": 0, "skipped": "config not found"}
    data = _read_jsonc(config_file, {})
    current = data.get("skills", [])
    if isinstance(current, str):
        current = [current]
    if not isinstance(current, list) or any(not isinstance(item, str) for item in current):
        raise ValueError(f"OpenCode skills must be a string array: {config_file}")
    kept = [item for item in current if item != skill_root]
    removed = len(current) - len(kept)
    if removed:
        data["skills"] = kept
        _write_json(config_file, data)
    return {"path": str(config_file), "removed": removed}


def remove_kimi_personal_entry(
    share_dir: Path, plugin_name: str, plugin_dir: Path
) -> dict[str, Any]:
    """Remove a Kimi personal-market entry only when its source matches ours."""
    share_dir = Path(share_dir).expanduser().resolve()
    plugin_dir = Path(plugin_dir).expanduser().resolve()
    entry_path = share_dir / "daimon" / "plugin-market" / "personal" / f"{plugin_name.lower()}.json"
    if not entry_path.exists():
        return {"path": str(entry_path), "removed": False, "skipped": "personal entry not found"}
    try:
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Kimi personal entry: {entry_path}: {exc}") from exc
    if not isinstance(entry, dict):
        raise ValueError(f"Kimi personal entry must be an object: {entry_path}")
    entry_id = str(entry.get("id") or entry.get("name") or "").lower()
    if entry_id != plugin_name.lower():
        return {"path": str(entry_path), "removed": False, "skipped": "plugin id mismatch"}
    source_value = next(
        (entry.get(key) for key in ("source", "sourcePath", "source_path", "path", "dir", "pluginDir")
         if isinstance(entry.get(key), str) and entry.get(key)),
        None,
    )
    if not source_value:
        return {"path": str(entry_path), "removed": False, "skipped": "source path missing"}
    source_path = Path(source_value).expanduser()
    if not source_path.is_absolute():
        source_path = (entry_path.parent / source_path).resolve()
    else:
        source_path = source_path.resolve()
    if source_path != plugin_dir:
        return {"path": str(entry_path), "removed": False, "skipped": "source path mismatch"}
    entry_path.unlink()
    result: dict[str, Any] = {"path": str(entry_path), "removed": True}
    if str(entry.get("status", "")).lower() in {"installed", "enabled", "active"}:
        result["warning"] = "Kimi client installation may still need removal from the Kimi UI"
    return result


def _copy_plugin(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.install-", dir=str(destination.parent)))
    try:
        shutil.copytree(source, staging / destination.name, symlinks=False)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging / destination.name, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _default_opencode_config(home: Path) -> Path:
    override = os.environ.get("OPENCODE_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    config_dir = os.environ.get("OPENCODE_CONFIG_DIR")
    if config_dir:
        config_dir_path = Path(config_dir).expanduser()
        return _existing_opencode_config(config_dir_path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    config_dir_path = (Path(xdg).expanduser() if xdg else home / ".config") / "opencode"
    return _existing_opencode_config(config_dir_path)


def _existing_opencode_config(config_dir: Path) -> Path:
    """Prefer an existing JSONC config, then JSON, then the JSON default."""
    jsonc = config_dir / "opencode.jsonc"
    json_file = config_dir / "opencode.json"
    if jsonc.is_file():
        return jsonc
    if json_file.is_file():
        return json_file
    return json_file


def _codex_root(path: Path) -> Path | None:
    path = Path(path).expanduser().resolve()
    for ancestor in (path, *path.parents):
        if ancestor.name == "plugins" and ancestor.parent.name == ".agents":
            return ancestor.parent.parent
    return None


def _codex_locations(args: argparse.Namespace, plugin_store: Path) -> tuple[Path, Path]:
    marketplace_file = (
        Path(args.codex_marketplace).expanduser().resolve()
        if args.codex_marketplace
        else plugin_store / "marketplace.json"
    )
    if marketplace_file.name != "marketplace.json":
        raise ValueError("Codex marketplace file must be named marketplace.json")
    expected_marketplace = plugin_store / "marketplace.json"
    if marketplace_file != expected_marketplace:
        raise ValueError("Codex marketplace file must be the plugin store's marketplace.json")
    marketplace_root = _codex_root(plugin_store)
    if marketplace_root is None:
        raise ValueError("Codex plugin store must use the <root>/.agents/plugins layout")
    return marketplace_file, marketplace_root


def _remove_codex_plugin(codex: str, plugin_name: str, marketplace_name: str) -> dict[str, Any]:
    selector = f"{plugin_name}@{marketplace_name}"
    try:
        result = _run_json_command([codex, "plugin", "remove", selector, "--json"])
        return {"removed": True, "selector": selector, "result": result}
    except RuntimeError as exc:
        detail = str(exc).lower()
        if any(token in detail for token in ("not installed", "not found", "no plugin", "does not exist")):
            return {"removed": False, "selector": selector, "skipped": "plugin not installed"}
        raise


def _gemini_plugin_dir(home: Path, name: str) -> Path:
    return Path(home).expanduser().resolve() / ".gemini/config/plugins" / name


def _gemini_import_names(home: Path) -> list[str]:
    manifest = Path(home).expanduser().resolve() / ".gemini/config/import_manifest.json"
    if not manifest.is_file():
        return []
    data = _read_json(manifest, {})
    imports = data.get("imports", [])
    if not isinstance(imports, list):
        raise ValueError(f"Gemini import record must be an array: {manifest}")
    names: list[str] = []
    for item in imports:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _run_agy(home: Path, arguments: list[str]) -> dict[str, Any]:
    """Run Antigravity CLI against the installer's home, not the process home."""
    agy = shutil.which("agy")
    if not agy:
        raise RuntimeError("agy executable not found")
    env = os.environ.copy()
    env["HOME"] = str(Path(home).expanduser().resolve())
    completed = subprocess.run(
        [agy, *arguments],
        text=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"agy {' '.join(arguments)} failed: {detail}")
    return {"ok": True, "output": completed.stdout.strip()}


def _run_json_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, encoding="utf-8")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    try:
        return json.loads(completed.stdout) if completed.stdout.strip() else {"ok": True}
    except json.JSONDecodeError:
        return {"ok": True, "output": completed.stdout.strip()}


def install(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.source_root).expanduser().resolve()
    home = Path(args.home).expanduser().resolve()
    plugin_store = Path(args.plugin_store).expanduser().resolve() if args.plugin_store else home / ".agents/plugins"
    plugin_dir = plugin_store / args.name
    version = args.version or f"0.1.0+local.{__import__('time').strftime('%Y%m%d%H%M%S')}"
    with tempfile.TemporaryDirectory(prefix="agent-plugin-build-") as temp:
        built = Path(temp) / args.name
        summary = build_plugin(repo_root, built, args.name, version, args.description)
        _copy_plugin(built, plugin_dir)

    results: dict[str, Any] = {"plugin": summary, "source": str(plugin_dir), "platforms": {}}
    failures: list[str] = []

    def attempt(platform: str, action: Any) -> None:
        try:
            results["platforms"][platform] = action()
        except (OSError, RuntimeError, ValueError) as exc:
            failures.append(platform)
            results["platforms"][platform] = {"installed": False, "error": str(exc)}

    if not args.skip_opencode:
        config_file = Path(args.opencode_config).expanduser() if args.opencode_config else _default_opencode_config(home)
        attempt("opencode", lambda: update_opencode_config(config_file, plugin_dir / "skills"))

    if not args.skip_codex:
        def install_codex() -> dict[str, Any]:
            marketplace_file, marketplace_root = _codex_locations(args, plugin_store)
            marketplace = update_marketplace(
                marketplace_file, marketplace_root, args.name, plugin_dir
            )
            codex = shutil.which("codex")
            codex_result: dict[str, Any] = {"marketplace": marketplace, "installed": False}
            if codex:
                _run_json_command(
                    [codex, "plugin", "marketplace", "add", str(marketplace_root), "--json"]
                )
                codex_result["install"] = _run_json_command(
                    [codex, "plugin", "add", f"{args.name}@{marketplace['marketplaceName']}", "--json"]
                )
                codex_result["installed"] = True
            else:
                codex_result["skipped"] = "codex executable not found"
            return codex_result

        attempt("codex", install_codex)

    if not args.skip_kimi:
        def register_kimi() -> dict[str, Any]:
            kimi = Path(args.kimi_register).expanduser() if args.kimi_register else None
            if not kimi or not kimi.is_file():
                return {
                    "registered": False,
                    "skipped": "Kimi plugin-builder register_personal.py not found",
                }
            command = [sys.executable, str(kimi), str(plugin_dir)]
            if args.kimi_share_dir:
                command.extend(["--share-dir", str(Path(args.kimi_share_dir).expanduser())])
            if args.kimi_daimon_bin:
                command.extend(["--daimon-bin", str(Path(args.kimi_daimon_bin).expanduser())])
            if args.kimi_node:
                command.extend(["--node", str(Path(args.kimi_node).expanduser())])
            return {"registered": True, "result": _run_json_command(command)}

        attempt("kimi-work", register_kimi)

    if not args.skip_gemini:
        attempt("gemini", lambda: _run_agy(home, ["plugin", "install", str(plugin_dir)]))

    results["failures"] = failures
    return results


def uninstall(args: argparse.Namespace) -> dict[str, Any]:
    """Remove this plugin's own source and native client references."""
    validate_plugin_name(args.name)
    home = Path(args.home).expanduser().resolve()
    plugin_store = Path(args.plugin_store).expanduser().resolve() if args.plugin_store else home / ".agents/plugins"
    plugin_dir = plugin_store / args.name
    results: dict[str, Any] = {"name": args.name, "source": str(plugin_dir), "platforms": {}}
    failures: list[str] = []

    def attempt(platform: str, action: Any) -> None:
        try:
            results["platforms"][platform] = action()
        except (OSError, RuntimeError, ValueError) as exc:
            failures.append(platform)
            results["platforms"][platform] = {"removed": False, "error": str(exc)}

    if not args.skip_opencode:
        config_file = Path(args.opencode_config).expanduser() if args.opencode_config else _default_opencode_config(home)
        attempt("opencode", lambda: remove_opencode_config(config_file, plugin_dir / "skills"))

    if not args.skip_codex:
        def uninstall_codex() -> dict[str, Any]:
            marketplace_file, marketplace_root = _codex_locations(args, plugin_store)
            marketplace_name = MARKETPLACE_NAME
            if marketplace_file.exists():
                data = _read_json(marketplace_file, {})
                marketplace_name = data.get("name", MARKETPLACE_NAME)
                if not isinstance(marketplace_name, str) or not marketplace_name:
                    raise ValueError(f"marketplace name must be a non-empty string: {marketplace_file}")
            codex = shutil.which("codex")
            if not codex:
                raise RuntimeError(
                    "codex executable not found; native plugin cache was not removed"
                )
            native = _remove_codex_plugin(codex, args.name, marketplace_name)
            marketplace = remove_marketplace_entry(
                marketplace_file, marketplace_root, args.name, plugin_dir
            )
            return {"root": str(marketplace_root), "native": native, "marketplace": marketplace}

        attempt("codex", uninstall_codex)

    if not args.skip_kimi:
        def uninstall_kimi() -> dict[str, Any]:
            if not args.kimi_share_dir:
                raise RuntimeError(
                    "Kimi share directory not provided; set KIMI_SHARE_DIR to clean personal registration"
                )
            return remove_kimi_personal_entry(args.kimi_share_dir, args.name, plugin_dir)

        attempt("kimi-work", uninstall_kimi)

    if not getattr(args, "skip_gemini", False):
        def uninstall_gemini() -> dict[str, Any]:
            copy = _gemini_plugin_dir(home, args.name)
            has_record = args.name in _gemini_import_names(home)
            if not shutil.which("agy"):
                if not copy.exists() and not has_record:
                    return {"removed": False, "skipped": "agy executable not found"}
                raise RuntimeError("agy executable not found; Gemini copy or import record remains")
            if copy.exists():
                manifest = copy / "plugin.json"
                if not manifest.is_file():
                    raise RuntimeError(f"Gemini plugin.json missing; refusing to uninstall {copy}")
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Gemini plugin.json is not valid JSON; refusing to uninstall {copy}"
                    ) from exc
                if not isinstance(data, dict) or data.get("name") != args.name:
                    raise RuntimeError(
                        f"Gemini plugin.json name does not match {args.name}; refusing to uninstall {copy}"
                    )
            return _run_agy(home, ["plugin", "uninstall", args.name])

        attempt("gemini", uninstall_gemini)

    if not failures:
        def remove_source() -> dict[str, Any]:
            if not plugin_dir.exists():
                return {"path": str(plugin_dir), "removed": False, "skipped": "plugin source not found"}
            if plugin_dir.is_symlink() or not plugin_dir.is_dir():
                raise ValueError(f"plugin source is not a directory: {plugin_dir}")
            shutil.rmtree(plugin_dir)
            return {"path": str(plugin_dir), "removed": True}

        attempt("source", remove_source)

    results["failures"] = failures
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--home", default=Path.home(), type=Path)
    parser.add_argument("--plugin-store", type=Path)
    parser.add_argument("--name", default=DEFAULT_PLUGIN_NAME)
    parser.add_argument("--version")
    parser.add_argument("--description", default="Portable SDD skills for OpenCode, Codex, Kimi Work, and Gemini.")
    parser.add_argument("--opencode-config", type=Path)
    parser.add_argument("--codex-marketplace", type=Path)
    parser.add_argument("--kimi-register", type=Path)
    parser.add_argument("--kimi-share-dir", type=Path)
    parser.add_argument("--kimi-daimon-bin", type=Path)
    parser.add_argument("--kimi-node", type=Path)
    parser.add_argument("--skip-opencode", action="store_true")
    parser.add_argument("--skip-codex", action="store_true")
    parser.add_argument("--skip-kimi", action="store_true")
    parser.add_argument("--skip-gemini", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = uninstall(args) if args.uninstall else install(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
