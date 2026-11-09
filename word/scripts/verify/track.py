#!/usr/bin/env python3
"""Write tracked changes (w:ins / w:del) -- the revision WRITE side.

    python3 scripts/verify/track.py work/unpacked --ops plan.json --dry-run --author Agent
    # plan.json: [{"at": "#A1B2C3D4", "replace": "old", "with": "new"},
    #             {"after": "#A1B2C3D4", "new_paragraph": "..."},
    #             {"at": "#B2C3D4E5", "delete": "..."},
    #             {"at": "#C3D4E5F6", "del_paragraph": true},
    #             {"para": "Q3 revenue", "del_row": true},
    #             {"at": "#D4E5F6A1", "pfmt": "jc=center,num-id=7,ilvl=0"}]
    # single op: --at "#A1B2C3D4" --replace old --with new

## Addressing (two selectors, one discipline)

- `--at #ID` targets the view block line's stable #id and nothing else
  (ids never drift -> plan order is free). Any paragraph resolves: body,
  table cell, SDT, text box, and -- with `--part headerN.xml` /
  `footerN.xml` / `footnotes.xml` / `endnotes.xml` -- the other stories
  (prep backfills paraIds in every story part). Cell ids are not printed
  in the compact view; `read.py <unpacked> --raw N` shows them.
- `--para TEXT` targets the UNIQUE paragraph whose text contains TEXT,
  searched across the selected part (comment.py's anchor discipline:
  zero or multiple matches -> error, no guessing).
- The text-targeting ops (replace/delete/format-span/move-span) may omit
  both: their own target text resolves the paragraph, same uniqueness
  discipline. Structural ops (rows/columns/merge) always need one of
  --at/--para -- any paragraph inside the target row or cell.

## What one op can be

Text: replace / delete / append / new-paragraph / del-paragraph /
del-field (complex, fldSimple, and cross-paragraph fields).
Format: format-span + --fmt b/i/u=1/0 (rPrChange); --pfmt
jc/ind-left/ind-first/before/after/line/num-id/ilvl (pPrChange -- the
num-id/ilvl pair is how tracked NUMBERING changes are written: Word
records the numPr mutation as a pPrChange; numberingChange is a Word
2003 display artifact the resolver simply cleans up).
Table structure: del-row / ins-row (--before, --cells 'a|b|c') /
del-col / ins-col (--cells) / col-width (--width PT, --col N) /
merge-cells (--rows N). Row marks are trPr ins/del; column and merge
marks are tcPr cellIns/cellDel/cellMerge; width history is
tblGridChange (a CT_Markup element: w:id ONLY, no author/date).
Section: --sectfmt pg-w/pg-h/margin-*/orient/cols (sectPrChange; the
snapshot is CT_SectPrBase, so header/footer references stay live and
are preserved on reject).
Move: move-span + --to #ID (moveFrom/moveTo paired by range markers
sharing one w:name, Word's own shape). delete + --delete-end TEXT: a
cross-paragraph range inside ONE container (¶del merge shape).

Interface designed from field data: 84 hand-written revision edits across
one real 50-comment job hit exactly three pits, all absorbed here:
- run splitting at a boundary inside a non-text run -> refused with a
  clear error (same discipline as comment.py: no match / no guess);
- w:t -> w:delText and w:instrText -> w:delInstrText conversion is
  automatic (forgetting the latter is a validate violation);
- rPr for inserted text is cloned only from TEXT runs and stripped of
  anchor styles -- cloning from a commentReference run once dressed new
  body text in the comment-mark character style, invisible to the eye.

Revision ids are max+1 onward over the whole package; the paragraph-mark
rPr is ordered per CT_ParaRPr via ooxml_order. All edits of one
invocation are applied in memory and written once -- a failed
invocation writes nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
import opc  # noqa: E402  (shared OPC part resolution)
import revreg  # noqa: E402  (shared revision taxonomy: clone strips)
import walker as wml  # noqa: E402  (shared placeholder table + codec)
from comment import Ids, _runs_with_text, _split_run, _runs_offset_split  # noqa: E402  (shared anchor machinery + id allocator)
from coords import by_id  # noqa: E402  (the one #id resolver)
from ooxml_order import ensure_child, insert_ord, sort_children  # noqa: E402
from opc import atomic_write_tree  # noqa: E402

# Windows consoles/pipes default to the legacy ANSI code page (cp1252/cp936):
# the engine's CJK messages must never crash the gate there.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mark(root_tag: str, ids: Ids, author: str):
    el = etree.Element(W + root_tag)
    el.set(W + "id", ids.take())
    el.set(W + "author", author)
    el.set(W + "date", _now())
    return el


def _to_del_content(el) -> None:
    """w:t -> w:delText, w:instrText -> w:delInstrText, in place."""
    for t in el.iter(W + "t"):
        t.tag = W + "delText"
    for t in el.iter(W + "instrText"):
        t.tag = W + "delInstrText"


#: character styles that mark an ANCHOR, not an appearance. Cloning one
#: onto new text is the pollution this function was written to stop --
#: but it used to drop rStyle unconditionally, so replacing a word inside
#: a hyperlink or an Emphasis run produced plain text and silently lost
#: the character style (dxv2-6 review W1). Matched on styleId AND on the
#: built-in NAME, because Word localizes styleIds ("a3") while the
#: w:name of a built-in stays fixed.
_ANCHOR_STYLES = {
    "commentreference", "annotationreference", "footnotereference",
    "endnotereference", "linenumber", "pagenumber",
    "annotation reference", "footnote reference", "endnote reference",
    "line number", "page number",
}


#: styles.xml root for the package being edited, set once in main(). A
#: module-level slot rather than a parameter threaded through six call
#: sites -- the alternative was six chances to forget one.
_STYLES = [None]


def _is_anchor_style(sid: str, styles_root=None) -> bool:
    styles_root = styles_root if styles_root is not None else _STYLES[0]
    if (sid or "").lower() in _ANCHOR_STYLES:
        return True
    if styles_root is None:
        return False
    for st in styles_root.findall(W + "style"):
        if st.get(W + "styleId") != sid:
            continue
        nm = st.find(W + "name")
        val = (nm.get(W + "val") if nm is not None else "") or ""
        return val.lower() in _ANCHOR_STYLES
    return False


def _clone_rpr(run, styles_root=None):
    """Clone a TEXT run's rPr for new inserted text.

    Keeps rStyle -- a character style IS the run's appearance, and the
    tracked replacement of an Emphasis/Hyperlink word must stay italic /
    stay a link after accept. Only ANCHOR styles (comment/footnote
    references, line numbers) are stripped: those mark a position, and
    copying one onto ordinary text is what the original blanket drop was
    trying to prevent. Also strips ALL revision history
    (revreg.strip_history, recursive) -- history records are the SOURCE
    run's, and each carries a document-unique w:id a copy would
    duplicate."""
    rpr = run.find(W + "rPr") if run is not None else None
    if rpr is None:
        return None
    c = deepcopy(rpr)
    for st in c.findall(W + "rStyle"):
        if _is_anchor_style(st.get(W + "val") or "", styles_root):
            c.remove(st)
    revreg.strip_history(c)
    return c if len(c) else None


def _new_run(text: str, clone_from=None, color: str | None = None):
    """A plain run with cloned formatting; color overrides w:color (the
    direct-edit marking variant: replaced text shown in a review color
    WITHOUT tracked changes)."""
    r = etree.Element(W + "r")
    rpr = _clone_rpr(clone_from)
    if color:
        if rpr is None:
            rpr = etree.Element(W + "rPr")
        for c in rpr.findall(W + "color"):
            rpr.remove(c)
        cel = etree.Element(W + "color")
        cel.set(W + "val", color.upper())
        # insert_ord, NOT SubElement: a bare append lands AFTER an
        # rPrChange the clone might carry -- rPrChange must stay last
        # (the ordering helper existed all along; this path just did
        # not use it -- measured regression). _clone_rpr strips
        # rPrChange now, but the invariant belongs here regardless.
        insert_ord(rpr, cel)
    if rpr is not None and len(rpr):
        r.append(rpr)
    t = etree.SubElement(r, W + "t")
    t.text = text
    if text != text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _new_ins_run(text: str, ids: Ids, author: str, clone_from=None):
    ins = _mark("ins", ids, author)
    ins.append(_new_run(text, clone_from))
    return ins


def _field_zone(p):
    """Set of id(run) for every run living inside a complex field --
    instruction OR result region (begin..end, any nesting depth). A
    tracked edit in a RESULT region looks fine until Word updates fields
    and silently regenerates the cache over it; such spans are refused,
    not wrapped."""
    zone, depth = set(), 0
    for r in p.iter(W + "r"):
        fc = r.find(W + "fldChar")
        ty = fc.get(W + "fldCharType") if fc is not None else None
        if ty == "begin":
            depth += 1
        if depth > 0:
            zone.add(id(r))
        if ty == "end":
            depth = max(0, depth - 1)
    return zone


def _span_runs(p, target: str, ids: Ids | None = None):
    """Locate `target` inside paragraph p (across runs, splitting edges).
    -> list of fully-covered runs, in document order. Errors out on
    no match / multiple matches / boundary inside a non-text run.
    `ids` feeds _split_run: a split that clones an rPrChange assigns the
    clone a fresh document-unique id."""
    target = wml.decode_ph(target)     # view escape \(tab) -> literal
    runs = _runs_with_text(p)
    flat = "".join(t for _, t in runs)
    i = flat.find(target)
    if i < 0:
        raise SystemExit(
            f"target text not found in block: {target!r}. The match "
            "stream is the view's content line: (placeholders) like "
            "(tab)/(f1)/(img1) are not text -- split the target at "
            "them; \u00ab\u00bb-quoted text is tracked-DELETED (not in the "
            "accepted state) -- use revisions.py, not --replace. Run "
            "prep.py first to merge fragmented runs."
            + _near_miss(flat, target))
    if flat.find(target, i + 1) >= 0:
        raise SystemExit(f"target text matches multiple places in block: "
                         f"{target!r} -- lengthen it with context")
    j = i + len(target)
    # Refuse targets inside field territory BEFORE any splitting. Checking
    # only the seg for fldChar (below) misses two cases: a span strictly
    # inside a RESULT region touches no fldChar run, and fldSimple content
    # is nested, not a sibling. Both are cached text Word regenerates.
    zone = _field_zone(p)
    pos = 0
    for r, t in runs:
        if pos < j and pos + len(t) > i:        # run overlaps the target
            bad = id(r) in zone
            anc = r.getparent()
            while not bad and anc is not None and anc is not p:
                bad = anc.tag == W + "fldSimple"
                anc = anc.getparent()
            if bad:
                raise SystemExit(
                    "target text lies inside a field (instruction or "
                    "cached result) -- Word regenerates field results on "
                    "update, silently discarding edits there. Use "
                    "--del-field, or edit the text the field points at")
        pos += len(t)
    pos, start_run, end_run = 0, None, None
    for r, t in runs:
        if start_run is None and pos + len(t) > i:
            if pos < i:
                r = _split_run(r, i - pos, ids)
                t = t[i - pos:]
                pos = i
            start_run = r
        if start_run is not None and pos + len(t) >= j:
            if pos + len(t) > j:
                _split_run(r, j - pos, ids)
            end_run = r
            break
        pos += len(t)
    # collect the sibling chain start..end; refuse container-crossing spans
    if start_run.getparent() is not end_run.getparent():
        raise SystemExit("target text spans a container boundary "
                         "(hyperlink/ins/del/moveFrom/textbox); narrow "
                         "the target")
    parent = start_run.getparent()
    kids = list(parent)
    i0, i1 = kids.index(start_run), kids.index(end_run)
    seg = kids[i0:i1 + 1]
    for el in seg:
        if el.tag in (W + "del", W + "moveFrom") or (
                isinstance(el.tag, str)
                and el.find(W + "del") is not None):
            raise SystemExit(
                "target span contains tracked-deleted/moved-away "
                "content (the view shows it as «…») -- already-dead "
                "text cannot be re-deleted; narrow the target or use "
                "revisions.py to resolve the pending revision first")
    # Point markers and commentReference runs are ALLOWED in the span:
    # ops group around them (each contiguous run stretch gets its own
    # w:del) and the markers stay in place -- Word's own shape. This
    # used to be a refusal, which locked the CLI out of comment-driven
    # revision tasks where the text to edit is almost always inside an
    # anchor (measured: a runner hand-wrote 300 lines around it).
    # Fields stay refused: tearing a fldChar pair corrupts the file.
    for k in seg:
        if k.tag in _MARKER_TAGS:
            continue
        if k.tag != W + "r":
            raise SystemExit(
                f"span crosses a non-run element "
                f"({etree.QName(k).localname}) -- narrow the target so it "
                "stays inside plain text, or handle that element "
                "explicitly")
        if k.find(W + "commentReference") is not None:
            continue                       # boundary run, left in place
        if k.find(W + "fldChar") is not None or \
                k.find(W + "instrText") is not None:
            raise SystemExit("span crosses a field -- delete fields with "
                             "--del-field, or narrow the target")
    return seg


#: Point markers whose pair may sit outside the span: they act as group
#: boundaries and are never moved or wrapped.
_MARKER_TAGS = {W + t for t in (
    "bookmarkStart", "bookmarkEnd", "commentRangeStart",
    "commentRangeEnd", "permStart", "permEnd", "proofErr")}


def _is_group_run(el) -> bool:
    """A run that participates in del/replace groups (not a
    commentReference host, which is an anchor artifact, not content)."""
    return el.tag == W + "r" and el.find(W + "commentReference") is None


def _wrap_del(runs, ids: Ids, author: str):
    """Wrap a contiguous sibling run list in one w:del (converted)."""
    if not runs:
        return None
    parent = runs[0].getparent()
    d = _mark("del", ids, author)
    parent.insert(parent.index(runs[0]), d)
    for r in runs:
        parent.remove(r)
        _to_del_content(r)
        d.append(r)
    return d


def _wrap_del_grouped(seg, ids: Ids, author: str):
    """One w:del per contiguous run group in seg; markers and
    commentReference runs stay in place between the groups (pairing and
    anchor geometry preserved by construction). -> list of dels."""
    dels, group = [], []

    def flush():
        if group:
            dels.append(_wrap_del(list(group), ids, author))
            group.clear()
    for el in seg:
        if _is_group_run(el):
            group.append(el)
        else:
            flush()
    flush()
    return dels


def _wrap_all_runs_del(container, ids: Ids, author: str,
                       kids=None) -> int:
    """Wrap every run under container in w:del, grouping contiguous
    sibling runs; recurses into hyperlinks; runs inside someone's w:ins
    get a NESTED w:del (the correct reject-another's-insertion shape).
    `kids` limits the walk to an explicit sibling slice (field spans)."""
    n = 0
    group: list = []

    def flush():
        nonlocal n
        if group:
            _wrap_del(list(group), ids, author)
            n += len(group)
            group.clear()
    for child in (list(container) if kids is None else kids):
        if child.tag == W + "r":
            group.append(child)
        else:
            flush()
            if child.tag in (W + "hyperlink", W + "ins", W + "smartTag",
                             W + "sdt", W + "customXml", W + "dir",
                             W + "bdo", W + "fldSimple"):
                inner = child.find(W + "sdtContent") \
                    if child.tag == W + "sdt" else child
                if inner is not None:
                    n += _wrap_all_runs_del(inner, ids, author)
    flush()
    return n


def _mark_paragraph(p, tag: str, ids: Ids, author: str) -> None:
    """Set the paragraph-mark revision (¶del / ¶ins) with CT_ParaRPr
    ordering (ins/del sort before all format keys -- insert_ord knows).
    Idempotent per (tag): a mark of this kind already present is left
    alone -- writing a SECOND w:del/w:ins into one rPr is XSD-invalid
    (CT_ParaRPr allows at most one of each; dxv2-3 review P1.5c wrote
    two w:del deleting an already-mark-deleted paragraph)."""
    ppr = ensure_child(p, "pPr")
    rpr = ensure_child(ppr, "rPr")
    if rpr.find(W + tag) is not None:
        return
    insert_ord(rpr, _mark(tag, ids, author))


def _field_ranges(p, name: str):
    """Sibling-run ranges of fields whose instruction contains `name`
    (stack-based: fields nest). -> (closed, unclosed): closed is the
    list of [runs] (innermost wins); unclosed is [(begin_k, instr)] for
    fields that begin here but never close in this paragraph. Silently
    returning the truncated span as if it were the whole field was the
    measured failure (corpus: TOC fields spanning paragraphs) -- callers
    now choose cross-paragraph wrapping or refusal."""
    out, unclosed = [], []
    kids = list(p)
    k = 0
    while k < len(kids):
        el = kids[k]
        if el.tag == W + "r" and \
                el.find(f"{W}fldChar[@{W}fldCharType='begin']") is not None:
            depth, instr, seg, closed = 0, "", [], False
            for m in range(k, len(kids)):
                e2 = kids[m]
                seg.append(e2)
                if e2.tag != W + "r":
                    continue
                fc = e2.find(W + "fldChar")
                ty = fc.get(W + "fldCharType") if fc is not None else None
                if ty == "begin":
                    depth += 1
                elif ty == "end":
                    depth -= 1
                    if depth == 0:
                        closed = True
                        break
                for it in e2.iter(W + "instrText"):
                    instr += it.text or ""
            if name in instr:
                if closed:
                    out.append((k, k + len(seg) - 1, seg))
                else:
                    unclosed.append((k, instr))
            k += 1
            continue
        k += 1
    # innermost match wins: with nested fields, the outer span's
    # instruction CONTAINS the inner's -- deleting the outer 10-run field
    # because the target lives in the inner one is the measured failure
    inner = [x for x in out
             if not any(y is not x and x[0] <= y[0] and y[1] <= x[1]
                        for y in out)]
    return [seg for _, _, seg in inner], unclosed


def _del_field_cross(ref, unclosed, o, ids: Ids) -> int:
    """Fields beginning in `ref` but closing in a LATER sibling
    paragraph (TOCs): wrap begin..end across paragraphs in w:del, ¶del
    on fully-covered paragraphs. A begin nested inside another matching
    field's span is skipped (innermost wins -- the inner one gets its
    own walk). Fields that cross a non-paragraph block or never close
    in the container are refused: tearing a fldChar pair corrupts the
    file."""
    host = ref.getparent()
    kids = list(host)
    i0 = kids.index(ref)

    def walk(begin_el):
        """-> (end_p, end_run, nested_match) or (None, None, None)."""
        depth, started, nested = 0, False, False
        stack = []
        for pi in range(i0, len(kids)):
            blk = kids[pi]
            if blk.tag != W + "p":
                return None, None, None
            for el in blk.iter():
                if not started:
                    if el is not begin_el:
                        continue
                    started = True
                if el.tag != W + "r":
                    continue
                fc = el.find(W + "fldChar")
                ty = fc.get(W + "fldCharType") if fc is not None else None
                if ty == "begin":
                    depth += 1
                    stack.append("")
                elif ty == "end":
                    if stack:
                        instr = stack.pop()
                        if depth > 1 and o.del_field in instr:
                            nested = True
                    depth -= 1
                    if depth == 0:
                        return blk, el, nested
                for it in el.iter(W + "instrText"):
                    if stack:
                        stack[-1] += it.text or ""
        return None, None, None

    deleted = 0
    for begin_k, _instr in unclosed:
        begin_el = list(ref)[begin_k]
        end_p, end_el, nested = walk(begin_el)
        if end_p is None:
            raise SystemExit(f"--del-field: field {o.del_field!r} never "
                             "closes within this container (or crosses a "
                             "non-paragraph block) -- refused; tearing a "
                             "fldChar pair corrupts the file")
        if nested:
            continue                    # an inner field matches better
        i_end = kids.index(end_p)
        _wrap_all_runs_del(ref, ids, o.author, kids=list(ref)[begin_k:])
        for sib in kids[i0 + 1:i_end]:
            _wrap_all_runs_del(sib, ids, o.author)
            _mark_paragraph(sib, "del", ids, o.author)
        ep_kids = list(end_p)
        _wrap_all_runs_del(end_p, ids, o.author,
                           kids=ep_kids[:ep_kids.index(end_el) + 1])
        head_has_text = any(
            "".join(x.text or "" for x in el.iter(W + "t")).strip()
            for el in list(ref)[:begin_k])
        if not head_has_text:
            _mark_paragraph(ref, "del", ids, o.author)
        deleted += 1
    return deleted


def _fldsimple_to_runs(fs):
    """Replace a w:fldSimple with the equivalent complex field (begin /
    instrText / separate / result / end sibling runs). Needed because
    CT_RunTrackChange forbids fldSimple children: a tracked deletion must
    wrap RUNS -- and on accept the whole field is then really gone,
    whereas a w:del kept inside the fldSimple would leave an empty field
    shell that Word happily re-renders on the next update. Nested
    fldSimple children are converted first (depth-first).
    -> the new sibling elements, in document order."""
    for sub in list(fs.iterchildren(W + "fldSimple")):
        _fldsimple_to_runs(sub)

    def _run(child):
        r = etree.Element(W + "r")
        r.append(child)
        return r
    begin = etree.Element(W + "fldChar")
    begin.set(W + "fldCharType", "begin")
    instr = etree.Element(W + "instrText")
    instr.text = fs.get(W + "instr") or ""
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    sep = etree.Element(W + "fldChar")
    sep.set(W + "fldCharType", "separate")
    end = etree.Element(W + "fldChar")
    end.set(W + "fldCharType", "end")
    content = [c for c in fs if c.tag != W + "fldData"]
    new = [_run(begin), _run(instr), _run(sep)] + content + [_run(end)]
    parent, idx = fs.getparent(), fs.getparent().index(fs)
    for k, el in enumerate(new):
        parent.insert(idx + k, el)
    new[-1].tail, fs.tail = fs.tail, None
    parent.remove(fs)
    return new


def _near_miss(flat: str, target: str) -> str:
    """When the anchor misses, say HOW it missed. The killer case from
    the field: the document has U+2011 (non-breaking hyphen) where the
    caller typed U+002D -- two glyphs no human eye tells apart. Exact
    matching stays exact (loosening it would turn "not found" into
    "silently edited the wrong place"); the fix is to hand back the
    nearest text in the block with the first differing character NAMED
    by codepoint, so the caller corrects the anchor instead of
    bisecting by hand."""
    import difflib
    if not flat or not target:
        return ""
    win = len(target)
    grams = {flat[k:k + win] for k in range(0, max(1, len(flat) - win + 1))}
    best = difflib.get_close_matches(target, grams, n=1, cutoff=0.6)
    if not best:
        return ""
    cand = best[0]
    d = next((k for k in range(min(len(cand), len(target)))
              if cand[k] != target[k]), None)
    if d is None:
        return f"\n  nearest in block: {cand!r}"
    return (f"\n  nearest in block: {cand!r}"
            f"\n  first difference at char {d}: you wrote "
            f"U+{ord(target[d]):04X} {target[d]!r}, the document has "
            f"U+{ord(cand[d]):04X} {cand[d]!r}")


def _brief(what: str) -> str:
    """One-line summary of an applied op. `what` spells out the old and
    new text in full; on a batch that is the caller's own plan read back
    to them -- measured at 94% of the plan's token count for 26 ops.
    Keep the shape and the size, drop the payload; --verbose restores it."""
    m = re.match(r"-'(.*)' \+'(.*)'$", what, re.S)
    if m:
        old, new = m.group(1), m.group(2)
        # a replace usually rewrites a few characters inside a long
        # anchor; echoing both sides in full repeats the plan twice over.
        # Strip the shared head and tail and show only what MOVED.
        h = 0
        while h < min(len(old), len(new)) and old[h] == new[h]:
            h += 1
        t = 0
        while (t < min(len(old), len(new)) - h
               and old[len(old) - 1 - t] == new[len(new) - 1 - t]):
            t += 1
        do, dn = old[h:len(old) - t], new[h:len(new) - t]
        if h or t:
            return (f"-{len(old)}ch +{len(new)}ch  "
                    f"{_snip(do, 20)} -> {_snip(dn, 20)}"
                    + (f"  (@{h})" if h else ""))
        return f"-{len(old)}ch +{len(new)}ch {_snip(old)} -> {_snip(new)}"
    m = re.match(r"-'(.*)'$", what, re.S)
    if m:
        return f"-{len(m.group(1))}ch {_snip(m.group(1))}"
    m = re.match(r"\+'(.*)'$", what, re.S)
    if m:
        return f"+{len(m.group(1))}ch {_snip(m.group(1))}"
    return what if len(what) <= 60 else what[:57] + "..."


def _snip(t: str, n: int = 14) -> str:
    t = t.replace("\n", " ")
    return repr(t if len(t) <= n else t[:n] + "\u2026")


def _blk_text(body, sel) -> str:
    """What the target paragraph ACTUALLY holds right now -- the fact
    the caller needs and the tool already had."""
    try:
        from coords import by_id
        el = by_id(body, sel)
    except BaseException:
        return ""
    return "".join(t.text or "" for t in el.iter(W + "t", W + "delText"))


def _op_error(k: int, o, e: BaseException, body) -> str:
    """Turn a bare refusal into something the caller can act on: WHICH
    op, WHICH paragraph, WHICH anchor, and what that paragraph actually
    says right now. (The old index-drift diagnosis died with positional
    selectors: #ids do not drift, so the whole E_STALE category of
    failure no longer exists.)"""
    blk = o.after if getattr(o, "new_paragraph", None) else o.block
    target = (o.replace or o.delete or o.del_field or o.append
              or o.new_paragraph or o.format_span or o.move_span
              or o.pfmt or o.sectfmt or o.para or "")
    head = f"op#{k}"
    if blk is not None:
        head += f" at[{blk}]"
    elif getattr(o, "para", None):
        head += f" para[{o.para[:24]!r}]"
    if target:
        head += f" anchor={_snip(str(target), 30)}"
    lines = [f"{head}: {e}"]
    if blk is not None:
        now = _blk_text(body, blk)
        if now:
            lines.append(f"  {blk} now reads: {_snip(now, 40)}")
    return "\n".join(lines)


_W14PARA = ("{http://schemas.microsoft.com/office/word/2010/wordml}"
            "paraId")


def _fresh_paraid(pool: set, seed: str) -> str:
    """Delegates to revreg.fresh_pid -- THE one allocator (v3.2)."""
    v = revreg.fresh_pid(seed, pool)
    pool.add(v)
    return v


# --------------------------------------------------------------------------
# paragraph resolution (the two selectors + the implicit text anchor)
# --------------------------------------------------------------------------

def _para_text(p) -> str:
    """The match stream as plain text -- same channel _span_runs
    searches (live text only; «deleted» text and placeholders stay
    out), so an anchor can never fake contiguity across two adjacent
    cells or reach into dead content."""
    return "".join(t for _, t in _runs_with_text(p))


def _unique_para(scope, text: str, what: str):
    """The UNIQUE paragraph in `scope` whose match stream contains
    `text` -- --para's resolver and the implicit anchor of the
    text-targeting ops. Same discipline as comment.py's place_anchor:
    zero or multiple matches -> SystemExit, no guessing."""
    text = wml.decode_ph(text)
    paras = [p for p in scope.iter(W + "p") if text in _para_text(p)]
    if not paras:
        raise SystemExit(
            f"--{what}: anchor {text!r} found in no paragraph of this "
            "part. The match stream is the view's content line: "
            "(placeholders) like (tab)/(f1) are not text, «…»-quoted "
            "text is tracked-deleted -- check the current view")
    if len(paras) > 1:
        raise SystemExit(
            f"--{what}: anchor {text!r} matches {len(paras)} paragraphs "
            "-- lengthen it with more context, or scope with --at #ID")
    return paras[0]


def _unique_field_holder(scope, name: str):
    """del-field without a selector: the UNIQUE paragraph in `scope`
    hosting a field whose instruction contains `name` (complex field,
    fldSimple, or the begin of a cross-paragraph one)."""
    holders = []
    for p in scope.iter(W + "p"):
        closed, unclosed = _field_ranges(p, name)
        if closed or unclosed or any(
                name in (fs.get(W + "instr") or "")
                for fs in p.iter(W + "fldSimple")):
            holders.append(p)
    if not holders:
        raise SystemExit(f"--del-field: no field with {name!r} in its "
                         "instruction found in this part")
    if len(holders) > 1:
        raise SystemExit(f"--del-field: field {name!r} found in "
                         f"{len(holders)} paragraphs -- pick one with "
                         "--at/--para")
    return holders[0]


def _enclosing(el, tag: str):
    """Nearest ancestor-or-self w:tag, or None. A cell paragraph inside
    a nested table belongs to the INNER table/row/cell -- exactly the
    scope a structural op should touch."""
    while el is not None and el.tag != W + tag:
        el = el.getparent()
    return el


# --------------------------------------------------------------------------
# format revisions (rPrChange / pPrChange)
# --------------------------------------------------------------------------

_FMT_KEYS = {
    "b": ("b", {"1": None, "0": "0"}),        # val None = bare <w:b/>
    "i": ("i", {"1": None, "0": "0"}),
    "u": ("u", {"1": "single", "0": "none"}),  # underline needs a w:val
}


def _parse_fmt(spec: str):
    out = []
    for part in spec.split(","):
        k, _, v = part.strip().partition("=")
        if k not in _FMT_KEYS or v not in _FMT_KEYS[k][1]:
            raise SystemExit(f"--fmt: bad setting {part!r} -- want "
                             "comma-separated b/i/u = 1/0, e.g. b=1,u=0")
        out.append((k, v))
    if not out:
        raise SystemExit("--fmt: empty spec")
    return out


def _apply_format(ref, o, ids: Ids) -> str:
    """Tracked FORMAT change (rPrChange) on a text span: the live rPr
    becomes the new state; the pre-change rPr is preserved inside
    rPrChange so reject restores it. Boolean three-state discipline:
    b=0 writes an explicit w:val="0" (cuts inheritance), never deletes
    the element into 'inherit'. A run already carrying rPrChange is
    refused -- stacking format revisions loses the intermediate state."""
    seg = _span_runs(ref, o.format_span, ids)
    changes = _parse_fmt(o.fmt)
    n = 0
    for el in seg:
        if not _is_group_run(el):
            continue
        rpr = el.find(W + "rPr")
        if rpr is None:
            rpr = el.makeelement(W + "rPr", {})
            el.insert(0, rpr)
        if rpr.find(W + "rPrChange") is not None:
            raise SystemExit(
                "a run in the span already carries an rPrChange -- "
                "accept/reject that format revision first")
        old = deepcopy(rpr)          # pre-change snapshot, no rPrChange
        for k, v in changes:
            tag, vals = _FMT_KEYS[k]
            for e in rpr.findall(W + tag):
                rpr.remove(e)
            e = etree.Element(W + tag)
            if vals[v] is not None:
                e.set(W + "val", vals[v])
            insert_ord(rpr, e)
        ch = _mark("rPrChange", ids, o.author)
        ch.append(old)
        insert_ord(rpr, ch)          # rPrChange must stay last
        n += 1
    return f"fmt {o.fmt} on {o.format_span!r} ({n} runs)"


_PFMT_JC = {"left", "center", "right", "both"}


def _parse_pfmt(spec: str):
    """jc=center,ind-left=24,ind-first=12,before=6,after=6,line=1.5,
    num-id=7,ilvl=0 (indents/spacing in pt, line as multiplier).
    -> [(key, value)]"""
    out = []
    for part in spec.split(","):
        k, _, v = part.strip().partition("=")
        if k == "jc" and v in _PFMT_JC:
            out.append((k, v))
        elif k in ("ind-left", "ind-first", "before", "after"):
            try:
                tw = round(float(v) * 20)          # pt -> twips
            except ValueError:
                raise SystemExit(f"--pfmt: bad value {part!r}")
            if tw < 0:
                raise SystemExit(f"--pfmt: {k} wants pt >= 0, got {v!r}")
            out.append((k, tw))
        elif k == "line":
            try:
                ln = round(float(v) * 240)          # 1.5x -> 360
            except ValueError:
                raise SystemExit(f"--pfmt: bad value {part!r}")
            if ln <= 0:
                raise SystemExit(f"--pfmt: line wants > 0, got {v!r}")
            out.append((k, ln))
        elif k == "num-id":
            if not v.isdigit():
                raise SystemExit(f"--pfmt: num-id wants int >= 0 "
                                 f"(0 clears numbering), got {v!r}")
            out.append((k, int(v)))
        elif k == "ilvl":
            if not v.isdigit() or int(v) > 8:
                raise SystemExit(f"--pfmt: ilvl wants 0..8, got {v!r}")
            out.append((k, int(v)))
        else:
            raise SystemExit(f"--pfmt: bad setting {part!r} -- want "
                             "jc=left|center|right|both, ind-left/ind-"
                             "first/before/after=<pt>, line=<x>, "
                             "num-id=<n>, ilvl=<0..8>")
    if not out:
        raise SystemExit("--pfmt: empty spec")
    return out


def _get_or_make(ppr, tag: str):
    e = ppr.find(W + tag)
    if e is None:
        e = etree.Element(W + tag)
        insert_ord(ppr, e)
    return e


def _apply_pformat(ref, o, ids: Ids) -> str:
    """Tracked PARAGRAPH-format change (pPrChange): live pPr becomes the
    new state; the pre-change pPr is preserved inside pPrChange so
    reject restores it. Refusals: paragraph already carries pPrChange
    (stacking loses the intermediate), and sectPr-bearing paragraphs
    (section properties are --sectfmt's job). firstLine vs
    firstLineChars are two inheritance channels (Chars wins) -- setting
    firstLine removes the Chars twin; the old pPr snapshot keeps it, so
    reject restores both channels. The snapshot is CT_PPrBase: rPr (the
    paragraph mark) and sectPr are NOT part of it -- storing them made
    every pPr-with-mark paragraph XSD-invalid (60+ corpus files)."""
    changes = _parse_pfmt(o.pfmt)
    ppr = ensure_child(ref, "pPr")
    if ppr.find(W + "sectPr") is not None:
        raise SystemExit("--pfmt: paragraph carries a sectPr (section "
                         "break) -- use --sectfmt for section properties")
    if ppr.find(W + "pPrChange") is not None:
        raise SystemExit("paragraph already carries a pPrChange -- "
                         "accept/reject that revision first")
    old = deepcopy(ppr)              # pre-change snapshot: CT_PPrBase
    for drop in ("rPr", "sectPr"):   # shape -- CT_PPrChange forbids
        for e in old.findall(W + drop):  # rPr/sectPr in the stored pPr
            old.remove(e)
    for k, v in changes:
        if k == "jc":
            _get_or_make(ppr, "jc").set(W + "val", v)
        elif k in ("ind-left", "ind-first"):
            ind = _get_or_make(ppr, "ind")
            if k == "ind-left":
                ind.set(W + "left", str(v))
                for e in ind.findall(W + "leftChars"):
                    ind.remove(e)
            else:
                ind.set(W + "firstLine", str(v))
                for e in ind.findall(W + "firstLineChars"):
                    ind.remove(e)
        elif k in ("before", "after", "line"):
            sp = _get_or_make(ppr, "spacing")
            if k == "before":
                sp.set(W + "before", str(v))
            elif k == "after":
                sp.set(W + "after", str(v))
            else:
                sp.set(W + "line", str(v))
                sp.set(W + "lineRule", "auto")
        elif k == "num-id":
            if v == 0:
                numpr = ppr.find(W + "numPr")
                if numpr is not None:
                    ppr.remove(numpr)       # numId=0: numbering off
            else:
                numpr = ppr.find(W + "numPr")
                if numpr is None:
                    numpr = etree.Element(W + "numPr")
                    insert_ord(ppr, numpr)
                nid = numpr.find(W + "numId")
                if nid is None:
                    nid = etree.Element(W + "numId")
                    insert_ord(numpr, nid)  # CT_NumPr: ilvl before numId
                nid.set(W + "val", str(v))
        elif k == "ilvl":
            numpr = ppr.find(W + "numPr")
            if numpr is None:
                numpr = etree.Element(W + "numPr")
                insert_ord(ppr, numpr)
            il = numpr.find(W + "ilvl")
            if il is None:
                il = etree.Element(W + "ilvl")
                insert_ord(numpr, il)
            il.set(W + "val", str(v))
    ch = _mark("pPrChange", ids, o.author)
    ch.append(old)
    insert_ord(ppr, ch)              # pPrChange sorts last in CT_PPr
    return f"pfmt {o.pfmt} ({len(changes)} setting(s))"


# --------------------------------------------------------------------------
# table structure revisions (rows / columns / width / merge)
# --------------------------------------------------------------------------

def _check_table_shape(tbl, op: str) -> None:
    """Shared refusals for column/row structural ops: row-exception
    records desync on row edits, span bookkeeping is structural, and
    SDT-wrapped rows are invisible to the direct-child walk the ops
    use (vchecks' walker.rows sees them -- a table where the two counts
    disagree would be edited half-blind)."""
    if tbl.find(W + "tblPrEx") is not None:
        raise SystemExit(f"--{op}: the table has tblPrEx row-exception "
                         "records -- structural edits would desync "
                         "them; out of scope")
    if op != "col-width" and (
            tbl.find(".//" + W + "gridSpan") is not None or
            tbl.find(".//" + W + "vMerge") is not None):
        raise SystemExit(f"--{op}: the table carries gridSpan/vMerge -- "
                         "span bookkeeping is structural, out of scope")
    if len(tbl.findall(W + "tr")) != len(list(wml.rows(tbl))):
        raise SystemExit(f"--{op}: the table wraps rows in SDT -- "
                         "structural edits there stay out of scope")


#: revision marks a cloned cell must NOT inherit: the clone is a NEW
#: cell with its own fate -- copying the source cell's cellIns/cellDel/
#: cellMerge duplicates their document-unique w:ids (measured: del-col
#: then ins-row on one table cloned the marks and the gate flagged
#: duplicate revision ids). vMerge goes too (copying a merge corrupts
#: it), and so does every *Change history record.
_CELL_MARKS = ("cellIns", "cellDel", "cellMerge", "vMerge")


def _clone_tcpr(src_tcpr):
    """Clone a source cell's tcPr for a newly inserted cell: geometry
    (width/span/borders) stays, revision marks and property history
    go -- the new cell gets its own marks from the op creating it."""
    if src_tcpr is None:
        return None
    tcpr = deepcopy(src_tcpr)
    for tag in _CELL_MARKS:
        for e in tcpr.findall(W + tag):
            tcpr.remove(e)
    revreg.strip_history(tcpr)
    sort_children(tcpr)     # source files may carry pre-existing order
                            # quirks; clones must be clean
    return tcpr


def _del_row(tbl, tr, ids: Ids, author: str) -> str:
    """Tracked deletion of the anchored table row: w:trPr/w:del on the
    row + every content run in its cells wrapped in w:del (paragraph
    marks stay -- a cell must keep its w:p). Accept drops the row;
    reject unwraps the content."""
    _check_table_shape(tbl, "del-row")
    if tr.find(W + "tblPrEx") is not None:
        raise SystemExit("--del-row: the anchored row carries a "
                         "misplaced tblPrEx -- out of scope")
    trpr = tr.find(W + "trPr")
    if trpr is None:
        trpr = tr.makeelement(W + "trPr", {})
        tr.insert(0, trpr)
    if trpr.find(W + "del") is not None:
        raise SystemExit("--del-row: that row is already marked deleted")
    insert_ord(trpr, _mark("del", ids, author))
    n = 0
    for p in tr.iter(W + "p"):
        n += _wrap_all_runs_del(p, ids, author)
    return f"row deleted ({n} runs wrapped + trPr/del)"


def _ins_row(tbl, tr, o, ids: Ids) -> str:
    """Tracked row INSERTION: new w:tr with trPr/w:ins, cells cloned
    from the anchored row's tcPr via _clone_tcpr (geometry kept,
    revision marks stripped; rows carrying vMerge are refused
    outright), each cell's paragraph mark ¶ins, optional --cells text
    as w:ins runs."""
    _check_table_shape(tbl, "ins-row")
    if tr.find(W + "tblPrEx") is not None:
        raise SystemExit("--ins-row: the anchored row carries a "
                         "misplaced tblPrEx -- out of scope")
    if any(tc.find(W + "tcPr/" + W + "vMerge") is not None
           for tc in tr.findall(W + "tc")):
        raise SystemExit("--ins-row: the anchored row carries a vertical "
                         "merge -- merging-aware insertion stays out of "
                         "scope")
    cells_text = o.cells.split("|") if o.cells else []
    src_tcs = tr.findall(W + "tc")
    new_tr = etree.Element(W + "tr")
    trpr = etree.SubElement(new_tr, W + "trPr")
    insert_ord(trpr, _mark("ins", ids, o.author))
    for idx, src_tc in enumerate(src_tcs):
        tc = etree.SubElement(new_tr, W + "tc")
        tcpr = _clone_tcpr(src_tc.find(W + "tcPr"))
        if tcpr is not None:
            tc.append(tcpr)
        p = etree.SubElement(tc, W + "p")
        _mark_paragraph(p, "ins", ids, o.author)
        if idx < len(cells_text) and cells_text[idx]:
            clone = None
            for r in src_tc.iter(W + "r"):
                if "".join(x.text or "" for x in r.findall(W + "t")).strip():
                    clone = r
                    break
            p.append(_new_ins_run(cells_text[idx], ids, o.author,
                                  clone_from=clone))
    if o.before:
        tr.addprevious(new_tr)
    else:
        tr.addnext(new_tr)
    where = "before" if o.before else "after"
    return f"row inserted {where} anchored row ({len(src_tcs)} cells)"


def _col_index_of_cell(tc):
    """Column index of a cell in its row (position among the row's
    w:tc, honoring gridSpan offsets)."""
    tr = tc.getparent()
    col = 0
    for sib in tr.findall(W + "tc"):
        if sib is tc:
            return col
        gs = sib.find(W + "tcPr/" + W + "gridSpan")
        col += int(gs.get(W + "val")) if gs is not None else 1
    return None


def _row_col_cells(tr):
    """Map column index -> (cell, span) for a row, honoring gridSpan."""
    out = {}
    col = 0
    for tc in tr.findall(W + "tc"):
        gs = tc.find(W + "tcPr/" + W + "gridSpan")
        span = int(gs.get(W + "val")) if gs is not None else 1
        out[col] = (tc, span)
        col += span
    return out


def _del_col(tbl, col: int, ids: Ids, author: str) -> str:
    """Tracked column deletion: tcPr/w:cellDel on every cell of the
    anchored column + each cell's content wrapped in w:del (paragraph
    marks stay -- a cell keeps its w:p). Accept removes the cells AND
    the gridCol (revisions.py's bookkeeping); reject restores content
    and drops the marks."""
    _check_table_shape(tbl, "del-col")
    if tbl.find(W + "tblGrid") is None:
        raise SystemExit("--del-col: the table has no tblGrid")
    n = 0
    for row in tbl.findall(W + "tr"):
        hit = _row_col_cells(row).get(col)
        if hit is None:
            continue
        tc, _span = hit
        tcpr = tc.find(W + "tcPr")
        if tcpr is None:
            tcpr = tc.makeelement(W + "tcPr", {})
            tc.insert(0, tcpr)
        if tcpr.find(W + "cellDel") is not None:
            raise SystemExit("--del-col: column already marked deleted")
        insert_ord(tcpr, _mark("cellDel", ids, author))
        for p in tc.iter(W + "p"):
            n += _wrap_all_runs_del(p, ids, author)
    return f"column {col} deleted ({n} runs wrapped + cellDel marks)"


def _ins_col(tbl, col: int, o, ids: Ids) -> str:
    """Tracked column insertion: new gridCol after the anchored column
    + each row gets a new cell there (tcPr via _clone_tcpr,
    tcPr/w:cellIns, ¶ins mark, optional --cells text as w:ins runs).
    Accept strips the marks (cells and gridCol stay); reject removes
    the cells and the gridCol (revisions.py's bookkeeping)."""
    _check_table_shape(tbl, "ins-col")
    grid = tbl.find(W + "tblGrid")
    if grid is None:
        raise SystemExit("--ins-col: the table has no tblGrid")
    cols = grid.findall(W + "gridCol")
    if not (0 <= col < len(cols)):
        raise SystemExit(f"--ins-col: column {col} out of range "
                         f"(0..{len(cols) - 1})")
    new_gc = deepcopy(cols[col])
    cols[col].addnext(new_gc)
    cells_text = o.cells.split("|") if o.cells else []
    for ri, row in enumerate(tbl.findall(W + "tr")):
        hit = _row_col_cells(row).get(col)
        if hit is None:
            continue
        tc, _span = hit
        new_tc = etree.Element(W + "tc")
        tcpr = _clone_tcpr(tc.find(W + "tcPr"))
        if tcpr is not None:
            new_tc.append(tcpr)
        tcpr2 = new_tc.find(W + "tcPr")
        if tcpr2 is None:
            tcpr2 = new_tc.makeelement(W + "tcPr", {})
            new_tc.insert(0, tcpr2)
        insert_ord(tcpr2, _mark("cellIns", ids, o.author))
        p = etree.SubElement(new_tc, W + "p")
        _mark_paragraph(p, "ins", ids, o.author)
        if ri < len(cells_text) and cells_text[ri]:
            clone = None
            for r in tc.iter(W + "r"):
                if "".join(x.text or "" for x in r.findall(W + "t")).strip():
                    clone = r
                    break
            p.append(_new_ins_run(cells_text[ri], ids, o.author,
                                  clone_from=clone))
        tc.addnext(new_tc)
    return f"column inserted after column {col} ({len(cols)} gridCols)"


def _col_width(tbl, col: int, o, ids: Ids) -> str:
    """Tracked column-width change: tblGrid/gridCol w:w updated, old
    tblGrid preserved in tblGridChange (reject restores it). Column is
    --col N (0-based, gridSpan-unaware) or the anchored cell's.
    --width is in points (twips = pt*20)."""
    _check_table_shape(tbl, "col-width")
    grid = tbl.find(W + "tblGrid")
    if grid is None:
        raise SystemExit("--col-width: the table has no tblGrid")
    cols = grid.findall(W + "gridCol")
    if not (0 <= col < len(cols)):
        raise SystemExit(f"--col-width: column {col} out of range "
                         f"(0..{len(cols) - 1})")
    try:
        tw = round(float(o.width) * 20)
    except (TypeError, ValueError):
        raise SystemExit(f"--col-width: bad width {o.width!r} (points)")
    if tw <= 0:
        raise SystemExit(f"--col-width: width wants > 0, got {o.width!r}")
    if grid.find(W + "tblGridChange") is not None:
        raise SystemExit("--col-width: tblGrid already carries a "
                         "tblGridChange -- accept/reject it first")
    old = deepcopy(grid)
    cols[col].set(W + "w", str(tw))
    # tblGridChange extends CT_Markup (w:id ONLY -- no author/date,
    # unlike the CT_TrackChange-based *Change siblings)
    ch = etree.Element(W + "tblGridChange")
    ch.set(W + "id", ids.take())
    ch.append(old)
    grid.append(ch)                  # tblGridChange sorts after gridCol
    return f"column {col} width -> {o.width}pt (tblGridChange)"


def _merge_cells(tbl, tr, col: int, o, ids: Ids) -> str:
    """Tracked vertical merge over --rows N rows (default 2): vMerge
    restart on the anchored cell, bare vMerge (continue) on the cells
    below, each carrying tcPr/cellMerge (no vMergeOrig -- the pre-merge
    state was 'no vMerge', so reject just strips vMerge); continuation
    cells' content wrapped in w:del (reject restores it, Word's own
    shape)."""
    _check_table_shape(tbl, "merge-cells")
    rows = tbl.findall(W + "tr")
    nrows = o.rows if getattr(o, "rows", None) else 2
    if nrows < 2:
        raise SystemExit("--merge-cells: --rows wants >= 2")
    i0 = rows.index(tr)
    if i0 + nrows > len(rows):
        raise SystemExit(f"--merge-cells: only {len(rows) - i0} row(s) "
                         "below the anchor")
    n = 0
    for k in range(nrows):
        hit = _row_col_cells(rows[i0 + k]).get(col)
        if hit is None:
            raise SystemExit(f"--merge-cells: no cell at column {col} "
                             f"in row {i0 + k}")
        tc, _span = hit
        tcpr = tc.find(W + "tcPr")
        if tcpr is None:
            tcpr = tc.makeelement(W + "tcPr", {})
            tc.insert(0, tcpr)
        if tcpr.find(W + "vMerge") is not None:
            raise SystemExit("--merge-cells: a target cell already "
                             "carries vMerge")
        vm = etree.Element(W + "vMerge")
        if k == 0:
            vm.set(W + "val", "restart")
        insert_ord(tcpr, vm)
        insert_ord(tcpr, _mark("cellMerge", ids, o.author))
        if k > 0:
            for p in tc.iter(W + "p"):
                n += _wrap_all_runs_del(p, ids, o.author)
    return f"cells merged over {nrows} rows ({n} runs wrapped)"


# --------------------------------------------------------------------------
# section properties (sectPrChange)
# --------------------------------------------------------------------------

def _sectfmt(scope, ref, o, ids: Ids) -> str:
    """Tracked section-properties change (sectPrChange) on the
    body-level sectPr (no selector) or a paragraph's pPr-sectPr
    (--at/--para): live sectPr updated, old sectPr preserved so reject
    restores it. Keys: pg-w/pg-h (pt), orient=portrait|landscape,
    margin-top/bottom/left/right (pt), cols (count). The snapshot is
    CT_SectPrBase: header/footer references are LIVE content, not
    section properties -- they stay out of the snapshot, and
    revisions.py's restore keeps the live ones."""
    if scope.tag != W + "body":
        raise SystemExit("--sectfmt only works on document.xml")
    if ref is not None:
        ppr = ref.find(W + "pPr") if ref.tag == W + "p" else None
        sect = ppr.find(W + "sectPr") if ppr is not None else None
        if sect is None:
            raise SystemExit("--sectfmt: the target paragraph has no "
                             "pPr-sectPr (it is not a section break)")
    else:
        sect = scope.find(W + "sectPr")
        if sect is None:
            raise SystemExit("--sectfmt: no body-level sectPr")
    if sect.find(W + "sectPrChange") is not None:
        raise SystemExit("--sectfmt: sectPr already carries a "
                         "sectPrChange -- accept/reject it first")
    changes = _parse_sectfmt(o.sectfmt)
    old = deepcopy(sect)
    for drop in ("headerReference", "footerReference"):
        for e in old.findall(W + drop):
            old.remove(e)      # snapshot is CT_SectPrBase: no hdr/ftr refs
    for k, v in changes:
        if k == "pg":
            pg = _get_or_make(sect, "pgSz")
            pg.set(W + "w", str(v[0]))
            pg.set(W + "h", str(v[1]))
        elif k == "orient":
            _get_or_make(sect, "pgSz").set(W + "orient", v)
        elif k.startswith("margin-"):
            _get_or_make(sect, "pgMar").set(W + k[7:], str(v))
        else:  # cols
            _get_or_make(sect, "cols").set(W + "num", str(v))
    ch = _mark("sectPrChange", ids, o.author)
    ch.append(old)
    sect.append(ch)                  # sectPrChange sorts last in CT_SectPr
    return f"sectfmt {o.sectfmt}"


def _parse_sectfmt(spec: str):
    out = []
    for part in spec.split(","):
        k, _, v = part.strip().partition("=")
        if k == "orient" and v in ("portrait", "landscape"):
            out.append((k, v))
        elif k in ("pg-w", "pg-h", "margin-top", "margin-bottom",
                   "margin-left", "margin-right"):
            try:
                tw = round(float(v) * 20)
            except ValueError:
                raise SystemExit(f"--sectfmt: bad value {part!r}")
            if tw <= 0:
                raise SystemExit(f"--sectfmt: {k} wants pt > 0")
            out.append((k, tw))
        elif k == "cols":
            if not v.isdigit() or int(v) < 1:
                raise SystemExit("--sectfmt: cols wants int >= 1")
            out.append((k, int(v)))
        else:
            raise SystemExit(f"--sectfmt: bad setting {part!r} -- want "
                             "pg-w/pg-h/margin-*/<pt>, orient, cols")
    if not out:
        raise SystemExit("--sectfmt: empty spec")
    pgw = {k: v for k, v in out}
    if ("pg-w" in pgw) != ("pg-h" in pgw):
        raise SystemExit("--sectfmt: pg-w and pg-h go together")
    if "pg-w" in pgw:
        out = [x for x in out if x[0] not in ("pg-w", "pg-h")] + \
            [("pg", (pgw["pg-w"], pgw["pg-h"]))]
    return out


# --------------------------------------------------------------------------
# moves and cross-paragraph deletion
# --------------------------------------------------------------------------

def _wrap_move_grouped(seg, ids: Ids, author: str):
    """_wrap_del_grouped's moveFrom twin: one w:moveFrom per contiguous
    run group, markers/commentReference hosts stay in place. NOTE: the
    move PAIRING does not live on the moveFrom/moveTo elements (their
    type CT_RunTrackChange has no w:name) -- it is expressed by the
    moveFromRangeStart/End + moveToRangeStart/End markers the caller
    adds around the groups, sharing one w:name."""
    def wrap(runs):
        if not runs:
            return None
        parent = runs[0].getparent()
        d = _mark("moveFrom", ids, author)
        parent.insert(parent.index(runs[0]), d)
        for r in runs:
            parent.remove(r)
            _to_del_content(r)
            d.append(r)
        return d
    group, out = [], []
    for el in seg:
        if _is_group_run(el):
            group.append(el)
        else:
            out.append(wrap(group))
            group = []
    out.append(wrap(group))
    return [d for d in out if d is not None]


def _move_span(scope, ref, o, ids: Ids) -> str:
    """Tracked MOVE: source span wrapped in w:moveFrom (delText), a
    w:moveTo with the text appended to the --to destination paragraph.
    Pairing is Word's own shape: moveFromRangeStart/End and
    moveToRangeStart/End markers (Start/End share one w:id per pair)
    carrying one shared w:name. Accept removes the source, reject
    removes the destination copy."""
    seg = _span_runs(ref, o.move_span, ids)
    first_run = next(el for el in seg if _is_group_run(el))
    dest_p = by_id(scope, o.to)
    name = f"mv{ids.next_id}"
    groups = _wrap_move_grouped(seg, ids, o.author)
    rs_id = ids.take()
    rs = etree.Element(W + "moveFromRangeStart")
    rs.set(W + "id", rs_id)
    rs.set(W + "name", name)
    rs.set(W + "author", o.author)   # CT_MoveBookmark requires
    rs.set(W + "date", _now())       # author + date
    re_ = etree.Element(W + "moveFromRangeEnd")
    re_.set(W + "id", rs_id)
    groups[0].addprevious(rs)
    groups[-1].addnext(re_)
    mt = _mark("moveTo", ids, o.author)
    mt.append(_new_run(o.move_span, clone_from=first_run))
    dest_p.append(mt)
    rs2_id = ids.take()
    rs2 = etree.Element(W + "moveToRangeStart")
    rs2.set(W + "id", rs2_id)
    rs2.set(W + "name", name)
    rs2.set(W + "author", o.author)
    rs2.set(W + "date", _now())
    re2 = etree.Element(W + "moveToRangeEnd")
    re2.set(W + "id", rs2_id)
    mt.addprevious(rs2)
    mt.addnext(re2)
    return f"moved {o.move_span!r} -> paragraph {o.to} ({name})"


def _delete_cross(ref, o, ids: Ids) -> str:
    """Cross-paragraph deletion inside ONE container (body / cell):
    start paragraph's tail + intermediate paragraphs (content + marks)
    + end paragraph's head wrapped in w:del, with ¶del on the start and
    intermediate marks -- Word's shape for a range deletion, so accept
    joins the end paragraph's remainder into the start paragraph.
    Paragraphs must be siblings of the same parent; a table between
    them is structural and refused."""
    start_p = ref
    host = start_p.getparent()
    end_paras = [p for p in host.iter(W + "p")
                 if o.delete_end in _para_text(p)]
    if not end_paras:
        raise SystemExit(f"--delete-end: anchor {o.delete_end!r} found "
                         "in no paragraph of this container")
    if len(end_paras) > 1:
        raise SystemExit(f"--delete-end: anchor {o.delete_end!r} matches "
                         f"{len(end_paras)} paragraphs -- lengthen it")
    end_p = end_paras[0]
    if end_p is start_p:
        raise SystemExit("--delete-end resolves to the same paragraph "
                         "-- use --delete alone")
    if end_p.getparent() is not host:
        raise SystemExit("--delete-end: the two paragraphs live in "
                         "different containers (cell/body) -- narrow to "
                         "one container")
    kids = list(host)
    i0, i1 = kids.index(start_p), kids.index(end_p)
    if i1 < i0:
        raise SystemExit("--delete-end paragraph comes BEFORE the "
                         "--delete paragraph -- swap the two")
    for sib in kids[i0 + 1:i1]:
        if sib.tag != W + "p":
            raise SystemExit("--delete-end: a non-paragraph block "
                             f"(<{etree.QName(sib).localname}>) sits "
                             "between the two paragraphs -- structural, "
                             "refused")
    # start paragraph: wrap [offset i .. end]
    flat = _para_text(start_p)
    i = flat.find(o.delete)
    if i < 0 or flat.find(o.delete, i + 1) >= 0:
        raise SystemExit(f"--delete: {o.delete!r} not unique in its "
                         "paragraph -- lengthen it")
    _, at = _runs_offset_split(start_p, i, ids)
    seg = [el for el in list(start_p)[list(start_p).index(at):]]
    _wrap_del_grouped(seg, ids, o.author)
    _mark_paragraph(start_p, "del", ids, o.author)
    # intermediate paragraphs: full content + mark
    for sib in kids[i0 + 1:i1]:
        _wrap_all_runs_del(sib, ids, o.author)
        _mark_paragraph(sib, "del", ids, o.author)
    # end paragraph: wrap [start .. offset j]
    e_flat = _para_text(end_p)
    ei = e_flat.find(o.delete_end)
    if ei < 0 or e_flat.find(o.delete_end, ei + len(o.delete_end)) >= 0:
        raise SystemExit(f"--delete-end: {o.delete_end!r} not unique in "
                         "its paragraph -- lengthen it")
    before, _ = _runs_offset_split(end_p, ei + len(o.delete_end), ids)
    seg2 = list(end_p)[:list(end_p).index(before) + 1]
    _wrap_del_grouped(seg2, ids, o.author)
    n_mid = i1 - i0 - 1
    return (f"cross-paragraph delete {o.delete!r} .. {o.delete_end!r} "
            f"({n_mid} paragraph(s) between)")


def _one_op(scope, ids: Ids, o, pidpool: set = None) -> tuple:
    """Validate and apply ONE op against the live tree.
    -> (op name, description, resolved paragraph | None). o carries the
    same fields as the CLI namespace; SystemExit on any invalid op
    (callers write nothing in that case -- transactional)."""
    ops = [name for name, v in (
        ("replace", o.replace), ("delete", o.delete), ("append", o.append),
        ("format", o.format_span), ("pfmt", o.pfmt),
        ("del-paragraph", o.del_paragraph),
        ("new-paragraph", o.new_paragraph),
        ("del-field", o.del_field),
        ("del-row", o.del_row), ("ins-row", o.ins_row),
        ("move", o.move_span),
        ("del-col", o.del_col), ("ins-col", o.ins_col),
        ("col-width", o.col_width), ("merge-cells", o.merge_cells),
        ("sectfmt", o.sectfmt)) if v]
    if len(ops) != 1:
        raise SystemExit(
            "E_OP_SHAPE: exactly one operation per op | got a mix or none "
            "of replace/delete/append/format_span/pfmt/del_paragraph/"
            "new_paragraph/del_field/del_row/ins_row/move_span/del_col/"
            "ins_col/col_width/merge_cells/sectfmt")
    op = ops[0]
    # --- payload pairing rules (one line per measured mistake) ---
    if o.block is not None and o.para is not None:
        raise SystemExit("E_OP_SHAPE: at and para are alternative "
                         "selectors | give one, not both")
    if op == "replace" and o.with_ is None:
        raise SystemExit("E_OP_SHAPE: replace needs with | try: "
                         "{'at': '#id', 'replace': OLD, 'with': NEW}")
    if op == "format" and o.fmt is None:
        raise SystemExit("E_OP_SHAPE: format_span needs fmt | try: "
                         "{'format_span': TEXT, 'fmt': 'b=1,u=0'}")
    if op == "move" and not o.to:
        raise SystemExit("E_OP_SHAPE: move_span needs to | try: "
                         "{'move_span': TEXT, 'to': '#id'}")
    if op == "col-width" and o.width is None:
        raise SystemExit("E_OP_SHAPE: col_width needs width (points)")
    if op == "new-paragraph" and o.after is None and o.block is None \
            and o.para is None:
        raise SystemExit("E_OP_SHAPE: new_paragraph needs after/at/para "
                         "| try: {'after': '#id', 'new_paragraph': '...'}")
    if o.delete_end and op != "delete":
        raise SystemExit("E_OP_SHAPE: delete_end goes with delete")
    if getattr(o, "cells", None) and op not in ("ins-row", "ins-col"):
        raise SystemExit("E_OP_SHAPE: cells goes with ins_row/ins_col")
    if getattr(o, "before", None) and op != "ins-row":
        raise SystemExit("E_OP_SHAPE: before goes with ins_row")
    if getattr(o, "rows", None) and op != "merge-cells":
        raise SystemExit("E_OP_SHAPE: rows goes with merge_cells")
    if getattr(o, "col", None) is not None and op != "col-width":
        raise SystemExit("E_OP_SHAPE: col goes with col_width")

    # --- resolve the target paragraph (body-level sectfmt needs none) ---
    sel_id = o.after if (op == "new-paragraph" and o.after is not None) \
        else o.block
    if op == "sectfmt" and sel_id is None and o.para is None:
        ref = None                       # body-level sectPr
    elif sel_id is not None:
        ref = by_id(scope, sel_id)
    elif o.para is not None:
        ref = _unique_para(scope, o.para, op)
    elif op in ("replace", "delete", "format", "move"):
        # the target text is its own anchor (comment.py's discipline:
        # unique match or a clear error -- never a guess)
        ref = _unique_para(scope, {"replace": o.replace,
                                   "delete": o.delete,
                                   "format": o.format_span,
                                   "move": o.move_span}[op],
                           {"format": "format-span",
                            "move": "move-span"}.get(op, op))
    elif op == "del-field":
        ref = _unique_field_holder(scope, o.del_field)
    else:
        raise SystemExit(
            f"E_OP_SHAPE: {op} needs a target paragraph | try: "
            "at='#id' (view block line, or --raw for cells) or "
            "para='anchor text'")

    if op in ("del-row", "ins-row", "del-col", "ins-col",
              "col-width", "merge-cells"):
        tr = _enclosing(ref, "tr")
        tbl = _enclosing(ref, "tbl")
        if tr is None or tbl is None:
            raise SystemExit(
                f"E_SCOPE: --{op}: the target paragraph is not inside "
                "a table | structural ops address a paragraph in the "
                "target row/column")

    if op == "format":
        what = _apply_format(ref, o, ids)
    elif op == "pfmt":
        what = _apply_pformat(ref, o, ids)
    elif op == "del-row":
        what = _del_row(tbl, tr, ids, o.author)
    elif op == "ins-row":
        what = _ins_row(tbl, tr, o, ids)
    elif op == "del-col":
        what = _del_col(tbl, _col_index_of_cell(_enclosing(ref, "tc")),
                        ids, o.author)
    elif op == "ins-col":
        what = _ins_col(tbl, _col_index_of_cell(_enclosing(ref, "tc")),
                        o, ids)
    elif op == "col-width":
        tc = _enclosing(ref, "tc")
        col = o.col if o.col is not None else _col_index_of_cell(tc)
        what = _col_width(tbl, col, o, ids)
    elif op == "merge-cells":
        what = _merge_cells(tbl, tr,
                            _col_index_of_cell(_enclosing(ref, "tc")),
                            o, ids)
    elif op == "sectfmt":
        what = _sectfmt(scope, ref, o, ids)
    elif op == "move":
        what = _move_span(scope, ref, o, ids)
    elif op == "replace":
        seg = _span_runs(ref, o.replace, ids)
        first_run = next(el for el in seg if _is_group_run(el))
        if getattr(o, "color", None):
            # mark variant: DIRECT edit + review color, no revision
            # elements (a redline gate will honestly read it as an
            # untracked edit -- that is the point of the mode)
            parent = first_run.getparent()
            parent.insert(parent.index(first_run),
                          _new_run(o.with_, clone_from=first_run,
                                   color=o.color))
            for el in seg:
                if _is_group_run(el):
                    parent.remove(el)
            what = (f"-{o.replace!r} +{o.with_!r} in color {o.color} "
                    "(DIRECT edit, no revision)")
        else:
            dels = _wrap_del_grouped(seg, ids, o.author)
            dels[-1].addnext(_new_ins_run(o.with_, ids, o.author,
                                          clone_from=first_run))
            what = f"-{o.replace!r} +{o.with_!r}"
    elif op == "delete":
        if o.delete_end:
            what = _delete_cross(ref, o, ids)
        else:
            _wrap_del_grouped(_span_runs(ref, o.delete, ids), ids,
                              o.author)
            what = f"-{o.delete!r}"
    elif op == "append":
        clone = None
        for r, t in reversed(_runs_with_text(ref)):
            if t.strip():
                clone = r
                break
        ref.append(_new_ins_run(o.append, ids, o.author, clone_from=clone))
        what = f"+{o.append!r} (appended)"
    elif op == "del-paragraph":
        k = _wrap_all_runs_del(ref, ids, o.author)
        _mark_paragraph(ref, "del", ids, o.author)
        what = f"paragraph deleted ({k} runs + mark)"
    elif op == "new-paragraph":
        p = etree.Element(W + "p")
        src_ppr = ref.find(W + "pPr") if ref.tag == W + "p" else None
        if src_ppr is not None:
            ppr = deepcopy(src_ppr)
            for drop in ("rPr", "sectPr"):
                for e in ppr.findall(W + drop):
                    ppr.remove(e)
            # ALL revision history, RECURSIVELY via the shared registry
            # (review #10: stripping only the direct pPrChange child
            # left numPr/numberingChange alive in the copy -- another
            # document-unique id duplicated). A brand-new paragraph
            # has no history.
            revreg.strip_history(ppr)
            if len(ppr):
                p.append(ppr)
        _mark_paragraph(p, "ins", ids, o.author)
        clone = None
        if ref.tag == W + "p":
            for r, t in _runs_with_text(ref):
                if t.strip():
                    clone = r
                    break
        p.append(_new_ins_run(o.new_paragraph, ids, o.author,
                              clone_from=clone))
        # a stable #id from birth, so later ops in this or the next plan
        # can target the paragraph the tool just made; only when the
        # part already binds w14 (post-prep trees always do)
        new_pid = ""
        if pidpool is not None and "http://schemas.microsoft.com/office/"\
                "word/2010/wordml" in (scope.getroottree()
                                       .getroot().nsmap or {}).values():
            new_pid = _fresh_paraid(pidpool,
                                    f"track:{o.new_paragraph[:24]}")
            p.set(_W14PARA, new_pid)
        ref.addnext(p)
        what = (f"new paragraph after [{sel_id or o.para}]"
                + (f" -> #{new_pid}" if new_pid else ""))
    else:                                   # del-field
        segs, unclosed = _field_ranges(ref, o.del_field)
        # fldSimple form of the same field: instruction is an ATTRIBUTE,
        # so the complex-field scan above never sees it
        simples = [fs for fs in ref.iter(W + "fldSimple")
                   if o.del_field in (fs.get(W + "instr") or "")]
        simples = [fs for fs in simples          # innermost match wins
                   if not any(d is not fs and o.del_field in
                              (d.get(W + "instr") or "")
                              for d in fs.iter(W + "fldSimple"))]
        seg_els = {id(e) for seg in segs for e in seg}
        simples = [fs for fs in simples          # already inside a matched
                   if not any(id(anc) in seg_els  # complex span
                              for anc in fs.iterancestors())]
        if not segs and not simples and not unclosed:
            raise SystemExit(f"no field with {o.del_field!r} in its "
                             f"instruction found in block {o.block or o.para}")
        for seg in segs:
            # whole sibling slice, not just runs: a REF result often sits
            # inside a hyperlink -- wrapping only top-level runs would
            # leave the linked half of the field alive
            _wrap_all_runs_del(ref, ids, o.author, kids=seg)
        for fs in simples:
            _wrap_all_runs_del(ref, ids, o.author,
                               kids=_fldsimple_to_runs(fs))
        n_cross = _del_field_cross(ref, unclosed, o, ids) if unclosed else 0
        what = (f"{len(segs) + len(simples) + n_cross} field(s) "
                f"matching {o.del_field!r} deleted")

    return op, what, ref


def main() -> int:
    ap = argparse.ArgumentParser(
        description="write tracked changes into an unpacked docx")
    ap.add_argument("target", help="prep.py's unpacked/ directory")
    ap.add_argument("--at", dest="block", metavar="#ID",
                    help="target paragraph by its stable #id (the view "
                         "block line's #A1B2C3D4; cells: read.py --raw "
                         "N shows them) -- ids never drift, batch order "
                         "is free")
    ap.add_argument("--para", metavar="TEXT",
                    help="alternative to --at: the UNIQUE paragraph "
                         "containing TEXT, searched across the selected "
                         "part (zero/multiple matches -> error)")
    ap.add_argument("--after", metavar="#ID",
                    help="insert the new paragraph after this one (#id)")
    ap.add_argument("--part", metavar="NAME",
                    help="story part to edit: document.xml (default), "
                         "headerN.xml, footerN.xml, footnotes.xml, "
                         "endnotes.xml")
    ap.add_argument("--to", metavar="#ID",
                    help="with --move-span: destination paragraph")
    ap.add_argument("--replace", metavar="OLD")
    ap.add_argument("--with", dest="with_", metavar="NEW")
    ap.add_argument("--delete", metavar="TEXT")
    ap.add_argument("--delete-end", metavar="TEXT",
                    help="with --delete: delete a cross-paragraph range "
                         "ending after TEXT in a LATER sibling paragraph")
    ap.add_argument("--append", metavar="TEXT")
    ap.add_argument("--del-paragraph", action="store_true")
    ap.add_argument("--new-paragraph", metavar="TEXT")
    ap.add_argument("--del-field", metavar="NAME",
                    help="delete field(s) whose instruction contains NAME")
    ap.add_argument("--format-span", metavar="TEXT",
                    help="tracked FORMAT revision on this text span "
                         "(rPrChange); needs --fmt")
    ap.add_argument("--fmt", metavar="SPEC",
                    help="format settings, comma-separated b/i/u = 1/0, "
                         "e.g. b=1 or b=0,i=1 (0 writes explicit "
                         "w:val=0, cutting inheritance)")
    ap.add_argument("--pfmt", metavar="SPEC",
                    help="tracked PARAGRAPH-format revision (pPrChange) "
                         "on the resolved paragraph: jc=left|center|"
                         "right|both, ind-left/ind-first/before/after="
                         "<pt>, line=<x>, num-id=<n>, ilvl=<0..8>, "
                         "comma-separated")
    ap.add_argument("--del-row", action="store_true",
                    help="tracked deletion of the table row holding the "
                         "target paragraph")
    ap.add_argument("--ins-row", action="store_true",
                    help="tracked insertion of a table row after the "
                         "anchored row (--before for before; --cells "
                         "'a|b|c' for cell text)")
    ap.add_argument("--before", action="store_true",
                    help="with --ins-row: insert before the anchored row")
    ap.add_argument("--cells", metavar="'a|b|c'",
                    help="with --ins-row/--ins-col: text for the new "
                         "cells, pipe-separated")
    ap.add_argument("--move-span", metavar="TEXT",
                    help="tracked move of TEXT to the --to paragraph "
                         "(moveFrom/moveTo)")
    ap.add_argument("--del-col", action="store_true",
                    help="tracked deletion of the table column holding "
                         "the target paragraph (cellDel marks)")
    ap.add_argument("--ins-col", action="store_true",
                    help="tracked insertion of a table column after the "
                         "anchored one (cellIns marks; --cells for "
                         "per-row text)")
    ap.add_argument("--col-width", action="store_true",
                    help="tracked column-width change (tblGridChange); "
                         "column via --col N or the anchored cell, "
                         "needs --width")
    ap.add_argument("--col", type=int, metavar="N",
                    help="0-based column index (with --col-width)")
    ap.add_argument("--width", metavar="PT",
                    help="with --col-width: new width in points")
    ap.add_argument("--merge-cells", action="store_true",
                    help="tracked vertical merge over --rows N rows "
                         "from the anchored cell (vMerge + cellMerge)")
    ap.add_argument("--rows", type=int, metavar="N",
                    help="with --merge-cells: rows to merge (default 2)")
    ap.add_argument("--sectfmt", metavar="SPEC",
                    help="tracked section-properties revision "
                         "(sectPrChange) on the body sectPr (or a "
                         "paragraph's pPr-sectPr via --at/--para): "
                         "pg-w/pg-h/margin-*/<pt>, orient, cols")
    ap.add_argument("--author", default="Agent")
    ap.add_argument("--color", metavar="RRGGBB",
                    help="with --replace: DIRECT edit, new text in this "
                         "color, no revision elements (marking mode)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve every op and report, write nothing "
                         "(same code path, only the write is skipped)")
    ap.add_argument("--verbose", action="store_true",
                    help="echo each op's full old/new text (default: "
                         "a one-line summary -- the plan is not news)")
    ap.add_argument("--ops", metavar="PLAN.json",
                    help="batch mode: JSON array of op objects (same "
                         "keys as the CLI flags, hyphens or underscores);"
                         " one process, one id scan, one atomic write. "
                         "--part is invocation-level, not a plan key")
    a = ap.parse_args()

    def _sel_norm(v, name):
        """Selector: '#A1B2C3D4' -- the stable paragraph id, nothing
        else. Positional indexes were removed with the v3 break: they
        drift on insert/delete and forced a plan-ordering rule."""
        if v is None:
            return v
        s = str(v).strip()
        if re.fullmatch(r"#?[0-9A-Fa-f]{8}", s):
            return "#" + s.lstrip("#")
        raise SystemExit(f"E_SELECTOR: {name} got {v!r} | must be "
                         "'#A1B2C3D4' (8 hex, copied from the view's "
                         "block line)")

    a.block = _sel_norm(a.block, "--at")
    a.after = _sel_norm(a.after, "--after")
    a.to = _sel_norm(a.to, "--to")

    if a.color:
        if not a.replace and not a.ops:
            ap.error("--color goes with --replace")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", a.color):
            ap.error("--color wants 6 hex digits, e.g. FF0000")

    if a.ops:
        import plan as _plan

        def _sel(v, name):
            try:
                return _sel_norm(v, name)
            except SystemExit as e:
                raise ValueError(str(e.code).replace("E_SELECTOR: ", ""))

        def _color(v, name):
            v = _plan.str_norm(v, name)
            if not re.fullmatch(r"[0-9A-Fa-f]{6}", v):
                raise ValueError(f"{name} wants 6 hex digits")
            return v

        def _int(v, name):
            if isinstance(v, bool):
                raise ValueError(f"{name} must be an integer, got {v!r}")
            if isinstance(v, str) and v.lstrip("-").isdigit():
                return int(v)
            if not isinstance(v, int):
                raise ValueError(f"{name} must be an integer, got {v!r}")
            return v

        def _num(v, name):
            if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                raise ValueError(f"{name} must be a number, got {v!r}")
            return str(v)

        op_list = _plan.load(
            a.ops,
            fields={"replace": _plan.str_norm, "with_": _plan.str_norm,
                    "delete": _plan.str_norm, "append": _plan.str_norm,
                    "new_paragraph": _plan.str_norm,
                    "del_field": _plan.str_norm,
                    "del_paragraph": _plan.bool_norm,
                    "block": _sel, "after": _sel, "color": _color,
                    "para": _plan.str_norm, "to": _sel,
                    "format_span": _plan.str_norm, "fmt": _plan.str_norm,
                    "pfmt": _plan.str_norm, "sectfmt": _plan.str_norm,
                    "del_row": _plan.bool_norm, "ins_row": _plan.bool_norm,
                    "del_col": _plan.bool_norm, "ins_col": _plan.bool_norm,
                    "col_width": _plan.bool_norm,
                    "merge_cells": _plan.bool_norm,
                    "before": _plan.bool_norm,
                    "cells": _plan.str_norm,
                    "delete_end": _plan.str_norm,
                    "move_span": _plan.str_norm,
                    "rows": _int, "col": _int, "width": _num,
                    "author": _plan.str_norm},
            aliases={"with": "with_", "at": "block"},
            defaults=dict(replace=None, with_=None, delete=None,
                          append=None, del_paragraph=False,
                          new_paragraph=None, del_field=None,
                          block=None, after=None, color=None,
                          para=None, to=None,
                          format_span=None, fmt=None, pfmt=None,
                          sectfmt=None, del_row=False, ins_row=False,
                          del_col=False, ins_col=False, col_width=False,
                          merge_cells=False, before=False, cells=None,
                          delete_end=None, move_span=None,
                          rows=None, col=None, width=None,
                          author=a.author))
    else:
        op_list = [a]

    # WHICH PART: --part selects the story; document.xml resolves
    # through the shared OPC resolver (a legally-renamed main part still
    # works), the other stories use their conventional names.
    part = a.part or "document.xml"
    if not re.fullmatch(r"(document|header\d+|footer\d+|footnotes|"
                        r"endnotes)\.xml", part):
        raise SystemExit(f"E_INPUT: --part {part!r} is not an editable "
                         "story part | want document.xml, headerN.xml, "
                         "footerN.xml, footnotes.xml or endnotes.xml")
    root_dir = Path(a.target)
    names = [str(p.relative_to(root_dir)).replace("\\", "/")
             for p in root_dir.rglob("*") if p.is_file()]

    def _read(n):
        p2 = root_dir / n
        return p2.read_bytes() if p2.is_file() else None

    if part == "document.xml":
        doc = root_dir / opc.main_part(_read, names)
        if not doc.exists():
            raise SystemExit(f"E_INPUT: missing {doc} | target must be an unpacked directory (prep.py output)")
        tree = etree.parse(str(doc))
        scope = tree.getroot().find(W + "body")
    else:
        doc = root_dir / "word" / part
        if not doc.exists():
            raise SystemExit(f"E_INPUT: missing {doc} | the package has "
                             f"no {part}")
        tree = etree.parse(str(doc))
        scope = tree.getroot()
    roots = [tree.getroot()]
    styles_root = None
    sp = doc.parent / "styles.xml"
    if sp.is_file():
        try:
            styles_root = etree.parse(str(sp)).getroot()
        except etree.XMLSyntaxError:
            styles_root = None
    _STYLES[0] = styles_root
    for f in sorted(doc.parent.rglob("*.xml")):
        if f == doc:
            continue
        try:                    # headers/footnotes/comments carry w:id too
            roots.append(etree.parse(str(f)).getroot())
        except etree.XMLSyntaxError:
            continue
    ids = Ids(*roots)
    first_id = ids.next_id
    # paraId pool for new paragraphs: every paraId/durableId anywhere in
    # the package, so a fresh id cannot collide (same domain rules as
    # prep's backfill)
    pidpool = {v for r in roots for el in r.iter(etree.Element)
               for k2, v in el.attrib.items()
               if k2.endswith("}paraId") or k2.endswith("}durableId")}

    # All ops apply in memory, ONE atomic write at the end: a failing op
    # anywhere leaves the file untouched (per-op invocations once meant
    # 35 processes x 35 full id scans on a single batch job). Targets
    # are #ids or unique text anchors, which do not drift -- plan order
    # is free by construction.
    msgs = []
    for k, o in enumerate(op_list):
        try:
            op, what, ref = _one_op(scope, ids, o, pidpool)
        except SystemExit as e:
            # WHERE, not just why. A 26-op batch used to fail with a bare
            # sentence about run fragmentation: no op index, no block, no
            # anchor, and often the wrong cause (dxv2-9 field report).
            raise SystemExit(_op_error(k, o, e, scope)) from None
        pid = ref.get(_W14PARA) if ref is not None else None
        loc = f"#{pid}" if pid else (o.after or o.block or o.para or part)
        msgs.append((k, op, loc, what))
    if getattr(a, "dry_run", False):
        # NOT a simulation: the identical code path ran, every refusal
        # fired, only the write is skipped. A separate "preview" engine
        # would be a second implementation of apply(), free to drift.
        for k, op, loc, what in msgs:
            print(f"op#{k} at[{loc}] {op}: "
                  f"{what if a.verbose else _brief(what)}")
        print(f"dry-run OK: {len(op_list)} op(s) resolve, "
              f"would use ids {first_id}..{ids.next_id - 1} -- nothing written")
        return 0
    atomic_write_tree(tree, doc)
    for k, op, loc, what in msgs:
        # QUIET by default: the plan you just wrote is not news. Full
        # old/new text was 94% of the plan's own size on a 26-op batch.
        print(f"op#{k} block[{loc}] {op}: {what if a.verbose else _brief(what)}")
    n = ids.next_id - first_id
    print(f"({len(op_list)} op(s), ids {first_id}..{ids.next_id - 1}, "
          f"{n} revision elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
