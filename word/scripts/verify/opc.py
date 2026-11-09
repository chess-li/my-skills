#!/usr/bin/env python3
"""OPC package plumbing shared by every tool: relationship-target
resolution, safe extraction, atomic writes.

Three failure classes this module exists to kill:
- each tool hand-rolling its own Target join drifts at the edges
  (`../`, percent-encoding, TargetMode="External", package-root
  absolute paths) -- one resolver, one set of edges;
- extracting a foreign docx without a path guard lets a hostile entry
  (`../x`, an absolute path, a symlink) write outside the destination;
- writing onto the target in place (tree.write / zip rebuild) leaves a
  half-written file when interrupted. The atomic pattern -- temp file
  in the SAME directory, then os.replace -- either fully succeeds or
  changes nothing. Same directory matters: /tmp is often a different
  mount, and a cross-device "move" degrades to copy+delete, which is
  exactly the non-atomic write this exists to prevent.
"""
from __future__ import annotations

import errno
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
import sys

# Windows consoles/pipes default to the legacy ANSI code page (cp1252/cp936):
# the engine's CJK messages must never crash the gate there.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- rels

def rel_target(*, target: str | None, base_part: str,
               target_mode: str | None = None) -> str | None:
    """Resolve a relationship Target against the part declaring it.
    KEYWORD-ONLY (review #14): a positional call with the arguments
    reversed resolved every header relationship to the base part
    itself, and a downstream fallback masked it -- the type system
    cannot catch a str/str swap, so the signature must.

    -> normalized part name ("word/media/image1.png"),
       None for External / empty targets,
       ValueError for targets that escape the package root (malformed;
       every caller must notice, not silently mis-resolve).

    base_part is the OWNING part ("word/document.xml" for
    word/_rels/document.xml.rels); "" means the package root
    (_rels/.rels). Percent-encoding is decoded PER SEGMENT and a decoded
    segment containing a separator is rejected -- decoding first and
    splitting second would let "a%2F..%2F.." smuggle a `..` past the
    stack. A leading "/" is package-root-absolute, not host filesystem.
    """
    if not target or target_mode == "External":
        return None
    stack = ([] if target.startswith("/")
             else list(PurePosixPath(base_part).parent.parts))
    if stack == ["."]:
        stack = []
    for seg in target.lstrip("/").split("/"):
        seg = unquote(seg)
        if "/" in seg or "\\" in seg:
            raise ValueError(f"encoded separator in Target segment: "
                             f"{target!r}")
        if seg in ("", "."):
            continue
        if seg == "..":
            if not stack:
                raise ValueError(f"Target escapes package root: {target!r}")
            stack.pop()
        else:
            stack.append(seg)
    return "/".join(stack) or None


def rels_owner(rels_name: str) -> str:
    """dir/_rels/name.rels -> the part owning it (dir/name);
    _rels/.rels -> "" (the package root)."""
    p = PurePosixPath(rels_name)
    owner = p.parent.parent / p.name[:-len(".rels")]
    s = str(owner)
    return "" if s in (".rels", "/.rels") else s.lstrip("/")


# ------------------------------------------------- part resolution (OPC)

_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
#: relationship types whose targets carry TEXT (a story). Anything here
#: is walked by read/validate/revisions; anything not is data.
STORY_RT = {_RT + k for k in ("header", "footer", "footnotes", "endnotes",
                              "comments")}


def _xml(reader, name):
    try:
        data = reader(name)
    except Exception:
        return None
    if data is None:
        return None
    try:
        from lxml import etree
        return etree.fromstring(data)
    except Exception:
        return None


def main_part(reader, names) -> str:
    """The main document part, resolved through _rels/.rels. NEVER a
    hardcoded path: OPC lets a package name it anything, and Word opens
    such a package fine.

    Shared by read/validate/revisions/track ON PURPOSE. Each tool used to
    decide for itself -- read resolved via rels, revisions matched the
    `word/` prefix -- so a main part at `doc/main.xml` was rendered by the
    reader, PASSED by the validator, and silently written through
    unchanged by `revisions.py --accept` with exit code 0 and the message
    "processed 0 revisions" (dxv2-6 review B4). Half-support is worse
    than no support: it reports success."""
    names = set(names)
    rr = _xml(reader, "_rels/.rels")
    if rr is not None:
        for rel in rr.findall(_PR + "Relationship"):
            if (rel.get("Type") or "") == _RT + "officeDocument":
                try:
                    nm = rel_target(target=rel.get("Target"), base_part="")
                except ValueError:
                    continue
                if nm and nm in names:
                    return nm
    return "word/document.xml"


def parts_by_type(reader, names) -> dict:
    """{"comments": "word/cmts9.xml", "header": [...], ...} -- EVERY
    consumer's answer to "where does this story live", derived once from
    the main part's relationships.

    This exists because `story_parts` alone was not enough: read.py kept
    THREE separate hand-rolled walkers (comments/notes, headers/footers,
    and the styles/numbering pair), each opening
    `word/_rels/document.xml.rels` and resolving against
    `base_part="word/document.xml"`. Adding a shared resolver without
    deleting them just made a fourth implementation, so a package whose
    main part is `doc/main.xml` rendered its body while its comment and
    footnote bodies vanished -- and validate still said PASSED (dxv2-7
    review P1.1). One concept, one implementation."""
    names = set(names)
    main = main_part(reader, names)
    out: dict = {"document": main}
    if main not in names:
        return out
    rels = f"{PurePosixPath(main).parent}/_rels/" \
           f"{PurePosixPath(main).name}.rels"
    rels = rels.lstrip("./")
    dr = _xml(reader, rels)
    KINDS = ("comments", "footnotes", "endnotes", "styles", "numbering",
             "settings", "commentsExtended", "commentsIds")
    MULTI = ("header", "footer")
    for k in MULTI:
        out[k] = []
    if dr is not None:
        for rel in dr.findall(_PR + "Relationship"):
            ty = (rel.get("Type") or "")
            try:
                nm = rel_target(target=rel.get("Target"), base_part=main)
            except ValueError:
                continue
            if not nm or nm not in names:
                continue
            for k in KINDS:
                if ty == _RT + k:
                    out.setdefault(k, nm)
            for k in MULTI:
                if ty == _RT + k:
                    out[k].append(nm)
    # name-pattern fallback, scoped to the main part's own directory so a
    # package cannot pick up a stray word/comments.xml that nothing links
    base = str(PurePosixPath(main).parent)
    for k in KINDS:
        cand = f"{base}/{k}.xml".lstrip("/")
        if k not in out and cand in names:
            out[k] = cand
    for k in MULTI:
        out[k] = sorted(set(out[k]) | {
            n for n in names
            if re.fullmatch(rf"{re.escape(base)}/{k}\d*\.xml", n)})
    return out


def story_parts(reader, names) -> set:
    """Every text-bearing part: the main document plus whatever its rels
    declare as header/footer/notes/comments -- by TYPE, not by name."""
    by = parts_by_type(reader, names)
    out = {by["document"]} if by.get("document") in set(names) else set()
    for k in ("comments", "footnotes", "endnotes"):
        if by.get(k):
            out.add(by[k])
    for k in ("header", "footer"):
        out |= set(by.get(k) or ())
    if not out:
        out = {n for n in names
               if re.fullmatch(r"word/(header\d*|footer\d*|footnotes|"
                               r"endnotes|comments)\.xml", n)}
    return out


# ---------------------------------------------------------------- unpack

#: Decompression caps. Generous for any real document (the largest
#: corpus file is ~21 MB packed), tight enough that a zip bomb -- a few
#: KB expanding to tens of GB -- dies with a clear message instead of
#: exhausting memory/disk. Declared sizes in the central directory can
#: lie, so enforcement is on the actually-decompressed bytes.
_MAX_PART = 256 * 1024 * 1024        # one entry
_MAX_TOTAL = 1024 * 1024 * 1024      # whole package


class CappedZip:
    """ZipFile wrapper enforcing the SAME decompression caps as
    unpack() on every read. The caps lived only in unpack(); prep/
    read/validate/revisions called ZipFile.read() directly, so a zip
    bomb entered through the main entry points unbounded
    (Ultra-review P1). Business scripts use THIS, never raw
    ZipFile.read()."""

    def __init__(self, src):
        self._z = zipfile.ZipFile(src)
        self._seen: dict = {}        # name -> decompressed size (once)
        names = [i.filename for i in self._z.infolist() if not i.is_dir()]
        from collections import Counter as _C
        #: EXPOSED, not enforced: validate must be able to open an
        #: ambiguous package in order to REPORT it (refusing at the door
        #: turned its own diagnostic into a crash). Paths that have to
        #: PICK one (unpack, the view) refuse; the reporter does not.
        self.duplicates = sorted(k for k, v in _C(names).items() if v > 1)

    def namelist(self):
        return self._z.namelist()

    def infolist(self):
        return self._z.infolist()

    def read(self, name) -> bytes:
        # streamed with the cap enforced per chunk: ZipFile.read()
        # would materialize the whole bomb before we could refuse.
        # The package total counts each DISTINCT entry once -- re-reading
        # one entry must not re-accumulate (a legit package copied part
        # by part was wrongly killed; dxv2-3 review P1.7).
        out, got = [], 0
        with self._z.open(name) as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                got += len(chunk)
                if got > _MAX_PART:
                    raise SystemExit(
                        f"zip entry {name!r} decompresses past "
                        f"{_MAX_PART} bytes: refusing (zip-bomb defense)")
                prior = self._seen.get(name, 0)
                if sum(self._seen.values()) - prior + got > _MAX_TOTAL:
                    raise SystemExit(
                        f"package decompresses past {_MAX_TOTAL} bytes "
                        "total: refusing (zip-bomb defense)")
                out.append(chunk)
        self._seen[name] = got
        return b"".join(out)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._z.close()
        return False


def unpack(src, dest) -> int:
    """Extract a .docx into dest with hostile-entry defense: entries
    that escape dest (`../x`, absolute paths, same-prefix siblings via
    resolve()) are skipped; symlink entries land as PLAIN FILES holding
    the link text (we write bytes ourselves and never recreate the
    link -- a symlink inside the tree would turn every later write into
    a write-through-attacker-path); decompressed sizes are capped
    (zip-bomb defense). -> number of files written."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    base = dest.resolve()
    n, total = 0, 0
    with zipfile.ZipFile(src) as z:
        # duplicate entry names: OPC forbids them and every reader picks
        # a different one. Unpacking silently kept the LAST, so the view
        # (and every edit) ran against a version nobody chose
        # (dxv2-4 review P1.9). Refuse at the door -- the package is
        # ambiguous, not repairable by guessing.
        seen: dict = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            seen[info.filename] = seen.get(info.filename, 0) + 1
        dups = sorted(k for k, v in seen.items() if v > 1)
        if dups:
            raise SystemExit(
                "package contains duplicate entries: "
                + ", ".join(dups[:5])
                + (f" (+{len(dups) - 5} more)" if len(dups) > 5 else "")
                + " -- OPC requires unique part names and readers "
                "disagree on which one wins; fix the package before "
                "editing (unzip -l to inspect)")
        # literal backslash in an entry name: part names are /-separated,
        # so this is non-OPC at best and hostile at worst -- on Windows
        # `word\document.xml` resolves INTO word/document.xml and the
        # extraction overwrites the real main part (pack-side had the
        # mirror-image hole: normalization collision, E_PACK_DUP_ENTRIES)
        backslash = sorted({info.filename for info in z.infolist()
                            if "\\" in info.filename})
        if backslash:
            raise SystemExit(
                "package contains backslash entry names: "
                + ", ".join(backslash[:5])
                + (f" (+{len(backslash) - 5} more)"
                   if len(backslash) > 5 else "")
                + " -- OPC part names are /-separated; on Windows such "
                "an entry would overwrite a different part on "
                "extraction; fix the package before editing")
        for info in z.infolist():
            tgt = (base / info.filename.lstrip("/")).resolve()
            if not (tgt == base or base in tgt.parents):
                continue
            if info.is_dir():
                tgt.mkdir(parents=True, exist_ok=True)
                continue
            with z.open(info) as fh:
                data = fh.read(_MAX_PART + 1)
            if len(data) > _MAX_PART:
                raise SystemExit(
                    f"{info.filename} decompresses past "
                    f"{_MAX_PART >> 20} MiB -- refusing (zip bomb?)")
            total += len(data)
            if total > _MAX_TOTAL:
                raise SystemExit(
                    f"package decompresses past {_MAX_TOTAL >> 20} MiB "
                    "in total -- refusing (zip bomb?)")
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(data)
            n += 1
    return n


# ---------------------------------------------------------------- atomic

#: A .docx open in Word/WPS is held with an exclusive handle, so the final
#: `os.replace` onto it fails: ACCESS_DENIED/SHARING_VIOLATION on Windows,
#: EACCES/EPERM on a read-only POSIX target. That is a user-environment
#: condition, not a defect in the edit that produced the bytes -- and by
#: then the package is already fully built. It must never surface as a
#: PermissionError traceback, and the built bytes must never be deleted.
_LOCK_WINERRORS = frozenset((5, 32, 33))   # ACCESS_DENIED/SHARING/LOCK
_LOCK_ERRNOS = frozenset(
    e for e in (getattr(errno, n, None)
                for n in ("EACCES", "EPERM", "EBUSY", "ETXTBSY"))
    if e is not None)
#: Suffixes an office app plausibly holds open -- decides whether the
#: directions may name Word/WPS or must stay generic.
_OFFICE_SUFFIXES = frozenset(
    (".docx", ".docm", ".dotx", ".dotm", ".odt", ".rtf", ".doc"))


def _errnos(*names) -> frozenset:
    return frozenset(e for e in (getattr(errno, n, None) for n in names)
                     if e is not None)


#: The write step's OTHER environment failures, found by 2026-09-22 E2E in
#: the chat sandbox: 0.4.9 guarded `os.replace` and nothing else, so a
#: read-only output directory still died inside `tempfile.mkstemp` (before
#: the guard could speak) and a target path that was an existing DIRECTORY
#: still died on EISDIR. Both are environment conditions with a concrete
#: remedy -- directions, not tracebacks.
_DIR_UNWRITABLE_ERRNOS = _errnos("EACCES", "EPERM", "EROFS")
_DIR_MISSING_ERRNOS = _errnos("ENOENT")
_NOT_A_DIR_ERRNOS = _errnos("ENOTDIR")
_IS_A_DIR_ERRNOS = _errnos("EISDIR")

#: One exit code for the whole family: "the artifact could not be written
#: to the path you asked for". docx.py has used 3 for the locked case
#: since 0.4.7; widening it keeps one number for one situation instead of
#: minting a code per cause. The E_ code on the first line says which.
EXIT_TARGET_UNWRITABLE = 3
EXIT_TARGET_LOCKED = EXIT_TARGET_UNWRITABLE   # 0.4.9 name, kept for callers


def _is_locked_target(exc: OSError) -> bool:
    """True when `exc` means 'someone else holds the target', not
    'the write itself went wrong'."""
    return (getattr(exc, "winerror", None) in _LOCK_WINERRORS
            or exc.errno in _LOCK_ERRNOS)


def _refuse(code: str, en: str, dst: Path, what_cn: str,
            fixes: list) -> "SystemExit":
    """The write step's ONE refusal shape: greppable English E_ line for
    tests/monitoring, then numbered Chinese directions for the model
    (see err() for why two channels). Always exit 3."""
    print(f"{code}: {en} | {dst}", file=sys.stderr)
    print(f"错误：{what_cn}：{dst}", file=sys.stderr)
    for i, fix in enumerate(fixes, 1):
        print(f"  {i}. {fix}", file=sys.stderr)
    return SystemExit(EXIT_TARGET_UNWRITABLE)


def open_temp_beside(dst):
    """Create the temp file next to `dst` -- the FIRST half of every
    artifact write (the second is replace_or_keep).

    Nothing has been built yet when this fails, so unlike the locked-target
    case there is no artifact to preserve and the directions say so. Causes
    we can name get exit 3 + directions; anything else (ENOSPC, ...) keeps
    raising, because the model cannot act on it anyway."""
    dst = Path(dst)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(dst.parent),
                                   prefix=dst.name + ".", suffix=".tmp")
        return fd, Path(tmp)
    except OSError as exc:
        where = dst.parent
        if exc.errno in _DIR_MISSING_ERRNOS:
            raise _refuse(
                "E_TARGET_DIR_MISSING",
                "the output directory does not exist", dst,
                "输出目录不存在，无法写入",
                [f"先创建目录：{where}",
                 "或者把输出路径改成一个已存在的目录下的文件名；",
                 "本次还没有产生任何文件，改好路径后重新运行同一条命令即可。"])
        if exc.errno in _NOT_A_DIR_ERRNOS:
            raise _refuse(
                "E_TARGET_NOT_A_DIR",
                "a component of the output path is not a directory", dst,
                "输出路径中有一段不是目录，无法写入",
                [f"检查这段路径是否写错：{where}",
                 "把输出路径改成一个合法的目录下的文件名；",
                 "本次还没有产生任何文件，改好路径后重新运行同一条命令即可。"])
        if exc.errno in _DIR_UNWRITABLE_ERRNOS:
            raise _refuse(
                "E_TARGET_DIR_UNWRITABLE",
                "the output directory is not writable", dst,
                "输出目录没有写入权限（只读目录或权限不足），无法写入",
                [f"把输出路径改成一个可写目录，例如当前工作目录或 /tmp；",
                 f"或者请用户放开该目录的写权限：{where}",
                 "本次还没有产生任何文件，改好路径后重新运行同一条命令即可。"])
        raise


def _keep_built(tmp: Path, dst: Path) -> Path:
    """Park the finished temp under a name the user can open directly
    (`out.docx.a1b2c3.docx`, not `...tmp`). Keeping the raw temp is the
    fallback -- losing the bytes is never an option."""
    try:
        kept = tmp.with_suffix(dst.suffix) if dst.suffix else tmp
        if kept != tmp:
            os.replace(tmp, kept)
        return kept
    except OSError:
        return tmp


def replace_or_keep(tmp, dst, *, done: str = "本次打包已完成") -> None:
    """`os.replace(tmp, dst)` for a user-facing artifact.

    THE write step for every artifact this skill produces. On success it
    is a plain atomic replace. When dst is held by another process the
    finished bytes are KEPT (never unlinked) and the caller is given
    directions instead of a traceback -- exit 3, matching docx.py's
    handling of the identical condition, so one situation reads the same
    whichever entry point the model called.

    Two channels on purpose (see err()): a greppable English E_ code for
    tests and monitoring, then Chinese directions for the model."""
    tmp, dst = Path(tmp), Path(dst)
    try:
        os.replace(tmp, dst)
        return
    except OSError as exc:
        if exc.errno in _IS_A_DIR_ERRNOS:
            # dst is an existing DIRECTORY with the artifact's name. The
            # package is finished, so park it -- but never remove the
            # directory ourselves: it may be the user's data, and
            # an earlier workbook validator shipped exactly this shape as a bug.
            kept = _keep_built(tmp, dst)
            raise _refuse(
                "E_TARGET_IS_DIR",
                "the target path exists and is a directory, not a file",
                dst, "目标路径是一个已存在的目录，不是文件，无法写入",
                [f"本次打包已完成，结果已完整保留在：{kept}",
                 "把输出路径改成一个文件名（不要指向已存在的目录）；",
                 "或者确认那个目录是历史残留、由用户删除后，"
                 "再重新运行同一条命令。"])
        if not _is_locked_target(exc):
            # Not a lock (full disk, bad path, ...): keep every caller's
            # original contract -- a failed write leaves no temp behind.
            # Only a LOCKED target is worth parking bytes for, because
            # only then are the bytes known-good and the retry trivial.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    kept = _keep_built(tmp, dst)
    # Naming Word/WPS is right for a .docx and actively misleading for an
    # internal state.json -- the holder is whatever plausibly holds THIS
    # suffix, so the directions stay followable either way.
    office = dst.suffix.lower() in _OFFICE_SUFFIXES
    # sp: CJK/Latin mixed text takes a space before the Latin run, and
    # docx.py's shipped wording already has it -- keep them identical.
    sp = " " if office else ""
    holder = f"{sp}Word/WPS 等程序" if office else "其他程序"
    print(f"E_TARGET_LOCKED: cannot replace the target file — it is held "
          f"by another process or not writable | {dst} | try: close the "
          f"app holding it and re-run; the finished file is kept at "
          f"{kept}", file=sys.stderr)
    print(f"错误：无法写入目标文件（可能正被{holder}占用，或当前用户没有"
          f"写入权限）：{dst}", file=sys.stderr)
    print(f"{done}，内容没有丢失，无需重做前面的步骤。按以下任一方式处理：",
          file=sys.stderr)
    print(f"  1. 结果已完整保留在临时文件：{kept}", file=sys.stderr)
    print(f"  2. 请用户关闭占用该文件的{holder}，然后重新运行同一条命令即可；",
          file=sys.stderr)
    print(f"  3. 或者把输出路径改成一个新文件名重新运行，另存为新文件；"
          f"也可以在关闭占用后直接把上面的文件重命名为 {dst.name}。",
          file=sys.stderr)
    raise SystemExit(EXIT_TARGET_LOCKED)


def atomic_write(path, data: bytes) -> None:
    """Write bytes so `path` is either fully old or fully new; a failed
    attempt leaves no temp file behind (a LOCKED target is the documented
    exception -- replace_or_keep parks the finished bytes)."""
    path = Path(path)
    fd, tmp = open_temp_beside(path)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    replace_or_keep(tmp, path, done="本次写入已完成")


def atomic_write_tree(tree, path) -> None:
    """lxml tree/element -> atomic file, in the serialization every tool
    here uses (declaration + UTF-8 + standalone)."""
    from lxml import etree
    atomic_write(path, etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", standalone=True))


def atomic_zip_rewrite(src, dst, replace: dict[str, bytes] | None = None,
                       ) -> None:
    """Copy zip src -> dst, substituting entries named in `replace`
    (name -> new bytes). Atomic: assembled next to dst, then replaced.
    With no replacements the bytes are copied verbatim (no recompression
    churn)."""
    src, dst = Path(src), Path(dst)
    with zipfile.ZipFile(src) as _z:
        _n = [i.filename for i in _z.infolist() if not i.is_dir()]
    if len(_n) != len(set(_n)):
        from collections import Counter as _C
        d = sorted(k for k, v in _C(_n).items() if v > 1)
        # THE write primitive refuses too, so no editor path can copy an
        # ambiguous package forward (dxv2-5 review P1.4)
        raise SystemExit(
            "refusing to rewrite a package with duplicate entries: "
            + ", ".join(d[:5]))
    if not replace:
        atomic_write(dst, src.read_bytes())
        return
    fd, tmp = open_temp_beside(dst)
    try:
        with os.fdopen(fd, "wb") as f, \
                CappedZip(src) as zin, \
                zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                # capped read, and LAZY: an entry being replaced is
                # never decompressed at all (the eager default argument
                # read it first -- dxv2-4 review P1.9)
                if item.filename in replace:
                    zout.writestr(item, replace[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    replace_or_keep(tmp, dst, done="本次改写已完成")


def _main() -> int:
    """CLI so the repack step gets the same atomicity as the tools:
        python3 scripts/verify/opc.py pack work/unpacked out.docx
        python3 scripts/verify/opc.py unpack in.docx work/unpacked
    A shell `zip -Xr` writes the target in place -- interrupt it and the
    docx is half a zip."""
    import sys as _sys
    a = _sys.argv[1:]
    if len(a) == 3 and a[0] == "pack":
        atomic_zip_dir(a[1], a[2])
        suf = Path(a[2]).suffix.lower()
        note = (f"  (main part typed as {suf[1:]})"
                if suf in MAIN_CT else "")
        print(f"packed {a[1]} -> {a[2]}{note}")
        return 0
    if len(a) == 3 and a[0] == "unpack":
        n = unpack(a[1], a[2])
        print(f"unpacked {n} files -> {a[2]}")
        return 0
    print(__doc__ and _main.__doc__)
    return 2


def file_hash(path) -> str:
    """Content fingerprint of a packed file."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root) -> str:
    """Content fingerprint of an unpacked directory: every file's path
    and bytes, order-independent of filesystem quirks. mtimes are
    useless here -- unzip sets them arbitrarily."""
    import hashlib
    root = Path(root)
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()



#: The main part's content type is what tells Word "document" from
#: "template". prep.py retypes a .dotx working copy to document so
#: python-docx can open it; packing back out to a .dotx has to undo
#: that, or the deliverable is a DOCX wearing a .dotx name and Word
#: will not offer it as a template (dxv2-7 review P1.6).
MAIN_CT = {
    ".docx": "application/vnd.openxmlformats-officedocument."
             "wordprocessingml.document.main+xml",
    ".dotx": "application/vnd.openxmlformats-officedocument."
             "wordprocessingml.template.main+xml",
    ".docm": "application/vnd.ms-word.document.macroEnabled.main+xml",
    ".dotm": "application/vnd.ms-word.template.macroEnabled.main+xml",
}


def retype_main(ct_xml: bytes, suffix: str) -> bytes:
    """Rewrite [Content_Types].xml's MAIN-part override to match `suffix`.
    Returns the input unchanged when the suffix is unknown or already
    right -- never invents an override that was not there."""
    want = MAIN_CT.get(suffix.lower())
    if not want:
        return ct_xml
    out = ct_xml
    for ct in MAIN_CT.values():
        if ct == want:
            continue
        if ct.encode() in out:
            out = out.replace(ct.encode(), want.encode())
    return out


def _declared_main_part(src_dir):
    """The officeDocument target declared by _rels/.rels -- read BY PATH,
    so a readdir-blind tree still resolves. None when absent/unparseable
    (the conventional word/document.xml is the caller's fallback)."""
    try:
        from lxml import etree
        root = etree.fromstring(
            (Path(src_dir) / "_rels" / ".rels").read_bytes())
    except Exception:
        return None
    for rel in root.findall(_PR + "Relationship"):
        if (rel.get("Type") or "") == _RT + "officeDocument":
            try:
                return rel_target(target=rel.get("Target"), base_part="")
            except ValueError:
                continue          # unresolvable rel: try the next one
    return None


def tree_main_part(src_dir, names=None):
    """Main-part presence in an unpacked tree: (main, listed, by_path).

    The OKC sandbox fs can make a rename-created file invisible to
    directory LISTING while it stays openable by path (stat fine, rglob
    blind) -- packing from the listing then silently drops the main
    document part and os.replace destroys the previous good file with a
    broken package (E_VIEW_RENDER cascade, 2026-09 incident). `listed`
    is the first candidate visible in the listing, `by_path` the first
    openable one; both follow the same declared-then-conventional order
    as main_part(). `main` is simply the first candidate (declared
    preferred) regardless of which one actually exists -- callers act
    on `listed`/`by_path`. `names` may reuse an already-built listing."""
    src_dir = Path(src_dir)
    if names is None:
        names = {str(p.relative_to(src_dir)).replace("\\", "/")
                 for p in src_dir.rglob("*") if p.is_file()}
    candidates = [c for c in (_declared_main_part(src_dir),
                              "word/document.xml") if c]
    listed = next((c for c in candidates if c in names), None)
    by_path = next((c for c in candidates if (src_dir / c).is_file()), None)
    return candidates[0], listed, by_path


def _workspace_manifest_parts(src_dir):
    """The part list prep recorded in work/state.json for ITS unpacked/
    -- the expected-set for the readdir quirk's non-skeleton victims
    (media and friends vanish from listings just the same). None
    anywhere else: pack stays manifest-free outside prep workspaces.
    Swap siblings (unpacked.new~/.old~) share the workspace's state.json
    (it sits beside the whole family), so they resolve to the same
    manifest -- recovery uses it to tell a complete staged tree from a
    crippled one."""
    src_dir = Path(src_dir)
    name = src_dir.name
    for suf in (".new~", ".old~"):
        if name.endswith(suf):
            name = name[:-len(suf)]
            break
    if name != "unpacked":
        return None
    try:
        import json as _json
        data = _json.loads((src_dir.parent / "state.json").read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    parts = data.get("parts")
    if not isinstance(parts, list) or \
            not all(isinstance(p, str) for p in parts):
        return None
    return set(parts)


# ------------------------------------------------------------ swap recovery
#
# CONVENTION: calls into one workspace (prep / pack / edit_docx) must be
# SERIALIZED per workspace -- this module takes no inter-process lock.
# The only guard against mistaking another process's in-flight swap for
# crash residue is the freshness heuristic in recover_swap (a leftover
# touched within SWAP_FRESH_SECONDS is treated as possibly live and
# refused, E_SWAP_ACTIVE). Keep concurrent writers away from the same
# work/ dir; the heuristic bounds the blast radius, it does not make
# concurrency safe.

SWAP_FRESH_SECONDS = 120


def _swap_siblings(d):
    """The staged/backup trees edit_docx's swap keeps next to `d`:
    `<name>.new~` (the post-edit tree being staged) and `<name>.old~`
    (the pre-edit backup)."""
    d = Path(d)
    return (d.parent / (d.name + ".new~"),
            d.parent / (d.name + ".old~"))


def _tree_packable(d) -> bool:
    """A tree can stand in for the workspace only when it is complete,
    not merely skeleton-shaped:
    - the package skeleton must exist BY PATH (the listing may be
      blind): the main document part, [Content_Types].xml, _rels/.rels;
    - those skeleton parts must be WELL-FORMED XML -- a path-present but
      truncated part is a crippled tree, not a recoverable one;
    - when prep's state.json part manifest is available, every recorded
      part must exist by path -- a skeleton-complete tree that silently
      lost a media part must fail recovery, not be crowned workspace."""
    from xml.etree import ElementTree as _ET
    d = Path(d)
    if not d.is_dir():
        return False
    _m, _listed, by_path = tree_main_part(d)
    if by_path is None:
        return False
    for bone in (by_path, "[Content_Types].xml", "_rels/.rels"):
        p = d / bone
        if not p.is_file():
            return False
        try:
            _ET.fromstring(p.read_bytes())
        except (OSError, _ET.ParseError):
            return False
    manifest = _workspace_manifest_parts(d)
    if manifest is not None and \
            any(not (d / part).is_file() for part in manifest):
        return False
    return True


def _tree_fresh(p, *, now=None) -> bool:
    """True when anything inside tree `p` was touched within
    SWAP_FRESH_SECONDS -- the only signal (no lock is held) that the
    tree may be ANOTHER process's in-flight swap staging rather than
    crash residue. Recovery must refuse fresh trees, never "clean" them."""
    import time
    now = time.time() if now is None else now
    p = Path(p)
    try:
        newest = p.stat().st_mtime
        for f in p.rglob("*"):
            try:
                newest = max(newest, f.stat().st_mtime)
            except OSError:
                pass
    except OSError:
        return False
    return now - newest < SWAP_FRESH_SECONDS


def _rename_aside(p, *, why: str) -> Path:
    """Move tree `p` out of the swap namespace WITHOUT deleting a byte:
    `<name>.<why>-<timestamp>`. The recovery paths never rmtree a tree
    they did not stage themselves -- quarantine beats deletion, always
    (a misidentified "leftover" is somebody's data). A rename failure
    (Windows file lock) is LOUD: E_SWAP_LOCKED, never a silent skip."""
    import time
    p = Path(p)
    ts = time.strftime("%Y%m%d-%H%M%S")
    aside = p.parent / f"{p.name}.{why}-{ts}"
    n = 0
    while aside.exists():
        n += 1
        aside = p.parent / f"{p.name}.{why}-{ts}.{n}"
    try:
        p.rename(aside)
    except OSError as e:
        raise err("E_SWAP_LOCKED",
                  f"cannot set {p.name} aside — another process is "
                  "holding files inside it (Word/WPS/antivirus/"
                  "indexer?); nothing was deleted or overwritten",
                  where=str(p),
                  fix=f"close whatever uses the tree and retry, or move "
                      f"it aside manually: mv '{p}' '{aside}' ({e})")
    return aside


def recover_swap(d, *, clean_stale: bool = True,
                 force: bool = False) -> str | None:
    """Self-heal an edit_docx swap that died mid-flight; -> a report
    line for the transcript (None = nothing was wrong).

    The swap is two renames with staged trees beside the workspace. A
    crash between them leaves NO workspace at all, and until now every
    downstream tool just broke on the missing tree (pack: E_PACK_MAIN_PART
    with guidance that sent the agent to prep -f) -- or worse, prep
    silently rebuilt from the baseline, stranding the edits inside a
    leftover nobody looked at (the 2026-09 unpacked.new~ incident).

    - a leftover touched within SWAP_FRESH_SECONDS may be ANOTHER
      process's in-flight swap (no lock is held -- per-workspace calls
      must be serialized, see the section header): refuse with
      E_SWAP_ACTIVE, touch nothing;
    - workspace present and packable: the leftovers are uncommitted
      debris (interrupted staging, or a backup whose final cleanup
      never ran) -- with `clean_stale`, RENAME them aside (timestamped,
      never deleted) and report the paths;
    - workspace MISSING, one leftover packable: rename it back into
      place (.new~ first -- it is the later state; falling back to
      .old~ means the edit never landed, and the report says so); the
      other tree is renamed aside, not deleted;
    - workspace missing and nothing packable, or a BROKEN workspace
      coexisting with leftovers: ambiguous -- refuse with manual
      recovery steps; never continue over a crippled tree. With
      `force` (prep -f) the ambiguous trees are renamed aside into
      quarantine instead, so the rebuild can proceed while every byte
      of the would-be-discarded edits stays on disk for manual review.

    This function never rmtrees a tree: recovery deals in renames only.
    A tree it cannot identify with certainty is somebody's data until
    proven otherwise -- quarantine beats deletion, always."""
    d = Path(d)
    new, old = _swap_siblings(d)
    present = [p for p in (new, old) if p.exists()]
    if not present:
        return None
    fresh = [p for p in present if _tree_fresh(p)]
    if fresh:
        raise err("E_SWAP_ACTIVE",
                  "swap leftover(s) were touched seconds ago — another "
                  "process is probably editing this workspace RIGHT NOW "
                  "(no inter-process lock is held; per-workspace calls "
                  "must be serialized), refusing to mistake live "
                  "staging for crash residue",
                  where=", ".join(str(p) for p in fresh),
                  fix="leave the other process alone and retry in a "
                      f"couple of minutes (>{SWAP_FRESH_SECONDS}s of "
                      "quiet); if you are certain nothing is running, "
                      "rename the leftover(s) aside manually")
    if _tree_packable(d):
        if not clean_stale:
            return None
        asides = [_rename_aside(p, why="stale") for p in present]
        return (f"⚠ swap recovery: {d} is intact; set aside stale swap "
                f"leftover(s) from an interrupted edit (renamed, NOT "
                f"deleted — inspect and remove manually): "
                f"{', '.join(str(a) for a in asides)}")

    def _quarantine(trees):
        asides = [_rename_aside(p, why="quarantine") for p in trees]
        return ("⚠ swap recovery (forced): ambiguous swap residue — "
                "set aside, NOT deleted, so prep can rebuild from the "
                "source: " + ", ".join(str(a) for a in asides)
                + " — 编辑内容（如有）已隔离到上述路径，请人工核对 "
                "(any edits inside survive ONLY there)")

    if d.exists():
        if not force:
            raise err("E_SWAP_RESIDUE",
                      "an interrupted edit left swap leftovers AND the "
                      "workspace itself is broken (package skeleton "
                      "incomplete or malformed) — refusing to guess "
                      "which tree is authoritative",
                      where=", ".join(str(p) for p in (d, new, old)
                                      if p.exists()),
                      fix="inspect the trees (the main part is usually "
                          "word/document.xml), move the good one onto "
                          f"{d.name} and delete the other leftover(s); "
                          "or prep -f rebuilds from the source — the "
                          "ambiguous trees are quarantined aside, NOT "
                          "deleted, so any edits inside survive for "
                          "manual review")
        return _quarantine([d, *present])
    for cand, applied in ((new, True), (old, False)):
        if _tree_packable(cand):
            try:
                cand.rename(d)
            except OSError as e:
                raise err("E_SWAP_RESIDUE",
                          f"recovery could not move {cand.name} into "
                          f"place",
                          where=str(d),
                          fix=f"move it manually: mv '{cand}' '{d}' "
                              f"({e})")
            other = old if cand == new else new
            aside = (_rename_aside(other, why="superseded")
                     if other.exists() else None)
            note = (f"; the other tree was set aside at {aside} "
                    f"(renamed, NOT deleted)" if aside else "")
            if applied:
                return (f"⚠ swap recovery: an interrupted edit left no "
                        f"{d}; restored the POST-EDIT tree from "
                        f"{cand.name} — the edit HAD landed and is now "
                        f"the workspace{note}")
            return (f"⚠ swap recovery: an interrupted edit left no {d} "
                    f"and the staged post-edit tree was unusable; "
                    f"restored the PRE-EDIT tree from {cand.name} — "
                    f"the interrupted edit was NOT applied, redo "
                    f"it{note}")
    if force:
        return _quarantine(present)
    raise err("E_SWAP_RESIDUE",
              "an interrupted edit left swap leftovers but none is a "
              "complete tree (skeleton missing/malformed, or parts "
              "recorded by prep are absent)",
              where=", ".join(str(p) for p in (new, old)
                              if p.exists()),
              fix="inspect the leftovers manually; prep -f rebuilds "
                  "from the source — the leftovers are quarantined "
                  "aside, NOT deleted, so any edits inside survive for "
                  "manual review")


def atomic_zip_dir(src_dir, dst) -> None:
    """Zip a directory into dst atomically (entry names are /-separated
    paths relative to src_dir). The main part's content type is retyped
    to match dst's extension.

    Two guards before dst is touched -- never overwrite a good file with
    a broken package:
    - separator normalization must not collide two disk files into one
      zip entry (a literal `word\\document.xml` file would silently
      REPLACE the real main part's content);
    - the package skeleton ([Content_Types].xml, _rels/.rels, the main
      document part) must be packable: missing from the LISTING but
      openable by path -> packed explicitly (readdir quirk rescue);
      missing by path too -> refused."""
    src_dir, dst = Path(src_dir), Path(dst)
    report = recover_swap(src_dir, clean_stale=False)
    if report:
        # a swap that died mid-flight left no tree to pack -- it was
        # just restored; never pack over a crippled tree silently
        print(report)
    all_paths = sorted(src_dir.rglob("*"))
    links = [p for p in all_paths if p.is_symlink()]
    if links:
        raise err("E_PACK_SYMLINK",
                  "unpacked tree contains symlinks — a link can smuggle "
                  "bytes from outside the tree into the package",
                  where=", ".join(str(p.relative_to(src_dir))
                                  for p in links[:5]),
                  fix="replace the link with a plain file; unpack never "
                      "creates links, so one here was planted")
    files = [p for p in all_paths if p.is_file()]
    entries = [str(p.relative_to(src_dir)).replace("\\", "/")
               for p in files]
    from collections import Counter
    dups = sorted(n for n, c in Counter(entries).items() if c > 1)
    if dups:
        raise err("E_PACK_DUP_ENTRIES",
                  "multiple files map to the same zip entry after "
                  "path-separator normalization",
                  where=", ".join(dups[:5])
                        + (f" (+{len(dups) - 5} more)"
                           if len(dups) > 5 else ""),
                  fix="a file with a literal backslash in its name is "
                      "impersonating a package part — remove it; the "
                      "previous output file was left untouched")
    names = set(entries)
    _main, listed, by_path = tree_main_part(src_dir, names)
    checks = []
    if listed is None:
        checks.append(("main document part", by_path,
                       "E_PACK_MAIN_PART"))
    for bone in ("[Content_Types].xml", "_rels/.rels"):
        if bone not in names:
            checks.append((bone,
                           bone if (src_dir / bone).is_file() else None,
                           "E_PACK_SKELETON"))
    rescued = []
    for label, by_path_name, code in checks:
        if by_path_name is not None:
            if by_path_name in rescued:
                continue      # pathological rels named the same file twice
            files.append(src_dir / by_path_name)
            rescued.append(by_path_name)
        else:
            raise err(code,
                      f"unpacked tree has no {label} — refusing to "
                      "pack a broken package",
                      where=str(src_dir),
                      fix="rebuild the working copy (prep -f) or "
                          "restore the tree from a known-good package; "
                          "the previous output file was left untouched")
    manifest = _workspace_manifest_parts(src_dir)
    if manifest is not None:
        gone = sorted(manifest - names)
        for m in gone:
            if (src_dir / m).is_file():
                if m not in rescued:
                    files.append(src_dir / m)
                    rescued.append(m)
            else:
                raise err("E_PACK_PARTS_MISSING",
                          f"{len(gone)} part(s) recorded by prep are "
                          f"missing from the tree (listing fault or "
                          f"accidental deletion): "
                          + ", ".join(gone[:5]),
                          where=str(src_dir),
                          fix="if unintentional, rebuild the workspace "
                              "(prep -f); if you removed the part(s) on "
                              "purpose, re-run prep -f from the current "
                              "best docx or delete work/state.json to "
                              "pack without the manifest guard")
    if rescued:
        files.sort()
        print(f"⚠ pack: {', '.join(rescued)} missing from the "
              f"directory listing but exists by path (filesystem "
              f"readdir inconsistency) — packed explicitly; other "
              f"parts may be affected too, re-run prep if the output "
              f"looks stale")
    fd, tmp = open_temp_beside(dst)
    try:
        with os.fdopen(fd, "wb") as f, \
                zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zout:
            for p in files:
                name = str(p.relative_to(src_dir)).replace("\\", "/")
                if name == "[Content_Types].xml":
                    zout.writestr(name, retype_main(p.read_bytes(),
                                                    dst.suffix))
                else:
                    zout.write(p, name)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    # The package is complete here. If dst is locked, the bytes are
    # parked and the caller gets directions -- they are NOT thrown away
    # (losing them forces the whole edit to be redone).
    replace_or_keep(tmp, dst)


def err(code: str, what: str, where: str = "", fix: str = "") -> SystemExit:
    """The ONE tool-error format: `E_CODE: what | where | try: fix`.
    English, dense, greppable, locating. Tests pin the CODE; the prose
    can be reworded freely. Guidance lines (non-error stdout) stay in
    the docs' language -- two channels, two voices, so a model can tell
    'this is directions' from 'this broke' at a glance."""
    parts = [f"{code}: {what}"]
    if where:
        parts.append(where)
    if fix:
        parts.append(f"try: {fix}")
    return SystemExit(" | ".join(parts))


class edit_docx:
    """python-docx over the unpacked working copy -- the bridge that
    makes work/unpacked/ the ONLY editable surface:

        with opc.edit_docx("work/unpacked") as doc:
            doc.paragraphs[0].add_run(" ...")

    Enter: zip the tree to a temp .docx and open it with python-docx.
    Exit (no exception): save + unpack back over the tree atomically-ish
    (unpack to a sibling temp dir, then swap). Exception inside the
    block: nothing is written. python-docx re-serializes the parts it
    touched -- byte shape may change, semantics do not; the gate is
    semantic. A swap that died mid-flight on a PREVIOUS run (stale
    .new~/.old~ leftovers, or the workspace itself missing) is healed
    by recover_swap() on entry -- never edited over, never ignored.
    CONCURRENCY: no lock is taken; calls on one workspace must be
    serialized (recover_swap refuses freshly-touched leftovers with
    E_SWAP_ACTIVE, but that heuristic is a guardrail, not a mutex)."""

    def __init__(self, unpacked):
        self.dir = Path(unpacked)
        self.tmp = None
        self.doc = None

    def __enter__(self):
        import tempfile
        import docx
        report = recover_swap(self.dir)
        if report:
            print(report)
        self.tmp = Path(tempfile.mkdtemp(prefix="edx"))
        self.pkg = self.tmp / "pkg.docx"
        atomic_zip_dir(self.dir, self.pkg)
        self.doc = docx.Document(str(self.pkg))
        return self.doc

    def __exit__(self, et, ev, tb):
        import shutil
        try:
            if et is None:
                self.doc.save(str(self.pkg))
                # stage the new tree BESIDE the target (same fs), so the
                # swap is two metadata renames -- the earlier version
                # cross-device-copied from /tmp between the renames,
                # leaving a whole-tree-copy-sized crash window with the
                # workspace absent (review item)
                new, old = _swap_siblings(self.dir)
                for leftover in (new, old):
                    if leftover.exists():
                        # entry's recover_swap already set any earlier
                        # residue aside -- a leftover HERE means another
                        # process is touching this workspace (the serial
                        # convention was violated). Quarantine it, never
                        # delete: it is somebody's in-flight data.
                        _rename_aside(leftover, why="preempted")
                try:
                    unpack(self.pkg, new)
                except BaseException:
                    # a partial staging must never survive: left behind,
                    # it is exactly the crippled .new~ the recovery pass
                    # would have to disambiguate later
                    shutil.rmtree(new, ignore_errors=True)
                    raise
                try:
                    self.dir.rename(old)
                except OSError as e:
                    # a process holding files inside the workspace
                    # (Word/WPS/antivirus/indexer) fails the FIRST
                    # rename -- the workspace is still untouched; fail
                    # loud, with the staged tree cleaned up
                    shutil.rmtree(new, ignore_errors=True)
                    raise err("E_SWAP_LOCKED",
                              "cannot set the workspace aside for the "
                              "swap — another process is holding files "
                              "inside it (Word/WPS/antivirus/indexer?)",
                              where=str(self.dir),
                              fix="close whatever uses the workspace "
                                  f"and redo the edit ({e})")
                try:
                    new.rename(self.dir)
                except BaseException as swap_exc:
                    try:
                        old.rename(self.dir)      # roll back the swap
                    except OSError as rb_err:
                        raise err("E_SWAP_ROLLBACK",
                                  "the swap failed AND rolling the "
                                  "workspace back failed",
                                  where=str(self.dir),
                                  fix=f"the pre-edit tree survives at "
                                      f"{old}, the post-edit tree at "
                                      f"{new} — move one onto "
                                      f"{self.dir.name} manually "
                                      f"({rb_err})")
                    if isinstance(swap_exc, OSError):
                        raise err("E_SWAP_FAILED",
                                  "could not move the staged tree into "
                                  "place — the workspace was rolled "
                                  "back, no edit was lost",
                                  where=str(self.dir),
                                  fix=f"retry the edit ({swap_exc})")
                    raise
                # readdir self-check BEFORE the rollback copy is dropped:
                # a swapped tree whose main part is invisible to listing
                # poisons the NEXT pack (the readdir quirk this module's
                # pack guard exists for). Stat-blind too = the swap
                # itself lost the file -- roll back while we still can.
                _m, listed, by_path = tree_main_part(self.dir)
                if listed is None and by_path is None:
                    try:
                        self.dir.rename(new)
                        old.rename(self.dir)    # roll back the swap
                        shutil.rmtree(new, ignore_errors=True)
                    except OSError as rb_err:
                        raise err("E_SWAP_ROLLBACK",
                                  "swap lost the main document part "
                                  "AND rollback failed",
                                  where=str(self.dir),
                                  fix=f"the pre-edit tree survives at "
                                      f"{old} — move it back manually "
                                      f"({rb_err})")
                    raise err("E_SWAP_MAIN_PART",
                              "the swapped-in tree lost its main "
                              "document part (filesystem swap fault) — "
                              "the edit was rolled back",
                              where=str(self.dir),
                              fix="the previous workspace was restored; "
                                  "retry the edit")
                # the pre-edit backup is this swap's own product and the
                # swap is confirmed good -- but quarantine still beats
                # deletion (a free undo); a locked backup must not fail
                # an edit that HAS landed, so report loudly instead
                try:
                    aside = _rename_aside(old, why="backup")
                    print(f"⚠ edit landed; the pre-edit backup was set "
                          f"aside at {aside} (kept, NOT deleted — "
                          f"remove it manually when satisfied)")
                except SystemExit:
                    print(f"⚠ edit landed, but the pre-edit backup at "
                          f"{old} could not be set aside or removed "
                          f"(another process is holding files inside "
                          f"it — Word/WPS/antivirus/indexer?). The "
                          f"workspace itself is complete; remove the "
                          f"backup manually once nothing holds it.")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)
        return False


if __name__ == "__main__":
    import sys
    sys.exit(_main())
