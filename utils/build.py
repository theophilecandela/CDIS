#!/usr/bin/env python

# Python 3 Standard Library
import os
import pathlib
import subprocess
import sys

# Pandoc
import pandoc
from pandoc.types import *

# Command-Line/Process Helpers
# ------------------------------------------------------------------------------
def call(*args):
    args = [str(arg) for arg in args]
    options = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "bufsize": 1,
    }
    process = subprocess.Popen(args, **options)
    for line in iter(process.stdout.readline, b""):
        print(line.decode("utf-8"), end="")
    while True:
        status = process.poll()
        if status is not None:
            break
    if status != 0:
        sys.exit(status)


def python(*args):
    return call("python", *args)


def doctest(*args):
    return call("python", "-m", "doctest", *args)


def pdflatex(*args):
    return call("pdflatex", *args)


# Misc. Helpers
# ------------------------------------------------------------------------------
def clean_latex_trash():
    extensions = ["dvi", "aux", "log", "fls", "fdb_latexmk"]
    cwd = pathlib.Path.cwd()
    with_ext = lambda ext: cwd.glob("*." + ext)
    for ext in extensions:
        for file in with_ext(ext):
            file.unlink()


# Document Processing
# ------------------------------------------------------------------------------
def transform(doc):

    # DEPRECATED
    #
    # Replace rules with anonymous headers (not perfect solution ...
    # will appear in the TOC. But good for separation purposes)
    # if False:
    #     todos = []
    #     for elt, path in pandoc.iter(doc, path=True):
    #         if isinstance(elt, HorizontalRule):
    #             todos.append(path[-1])
    #     for todo in todos:
    #         holder, i = todo
    #         holder[i] = Header(3, ("", [], []), [])

    divify(doc)
    handle_level_4_sections(doc)
    # print_sections(doc)
    proofify(doc)
    transform_image_format(doc)
    solve_toc_nesting(doc)
    anonymify(doc)
    #add_font_awesome(doc)
    #add_marginnote(doc)
    #flag_definitions(doc)
    return doc

def anonymify(doc):
    anonymous_headers = []
    for elt, path in pandoc.iter(doc, path=True):
        if isinstance(elt, Header):
            header = elt
            _, attr, inlines = header[:]
            _, classes, _ = attr
            if inlines == [] or "anonymous" in classes:
                holder, i = path[-1]
                anonymous_headers.append((holder, i))
    for (holder, i) in reversed(anonymous_headers):
        del holder[i]


# Examination of sections in proofs shows that this algo is borked.
# Try lvl by level.
# Note: print_section actually shows that the divification actually
# works as intended, but the PDF toc generation messes the stuff
# when lvl 3 sections are nested directly into lvl 1.
# HTML also fucks up the stuff (to be checked), but this is not
# the fault of this function.
def divify(doc, level=None):
    # Encapsulate section content -- separated by headers -- in divs.

    # Note for the HTML backend:
    #  - div.section turned into section automatically but ...
    #  - the TOC generation is broken. That happens because of the
    #    extra div hierarchy, not specifically the "section" class.
    #    reference: <https://github.com/jgm/pandoc/issues/997>;
    #    marked as wontfix.

    # Note: isse with references; the bibliography will be added later,
    # out of the section.

    if level is None:
        for level in reversed([1, 2, 3, 4]):
            divify(doc, level=level)
    else:
        sections = []
        for elt, path in pandoc.iter(doc, path=True):
            if isinstance(elt, Header) and elt[0] == level:
                # print(str(elt)[:100])
                header = elt
                holder, start = path[-1]
                for offset, elt_ in enumerate(holder[start:]):
                    if offset == 0:
                        continue
                    if isinstance(elt_, Header) and elt_[0] <= level:
                        end = start + offset
                        break
                else:
                    end = None
                assert holder[start:end]  # not empty, at least a header
                sections.append((holder, start, end))

        for section in reversed(sections):
            holder, start, end = section
            attr = ("", ["section"], [])
            div = Div(attr, holder[slice(start, end)])
            # print(div)
            holder[slice(start, end)] = [div]


def print_sections(doc):
    for elt, path in pandoc.iter(doc, path=True):
        if isinstance(elt, Header):
            header = elt
            level, attr, inlines = header[:]
            minidoc = Pandoc(Meta({}), [Plain(inlines)])
            title = pandoc.write(minidoc)
            depth = len(
                [holder for holder, index in path if isinstance(holder, Div)]
            )
            print(str(depth) + "> " + depth * 4 * " " + title, end="")

def handle_level_4_sections(doc):
    # TODO: find them, transform the header into an emphasized span,
    # insert it into the subsequent content if it makes sense.

    # TODO. Grmph. Adding "." at the end doesn't always make sense.

    # TODO: transfer the header id to the encloding div.section ?

    found = []
    for elt, path in pandoc.iter(doc, path=True):
        if isinstance(elt, Header):
            header = elt
            level, attr, inlines = header[:]
            if level == 4:
                span = Span(attr, [Strong(inlines), Str("."), Space()])
                holder, i = path[-1]
                assert isinstance(holder, list)
                found.append((holder, span))

    for holder, span in found:
        assert isinstance(holder[0], Header)
        del holder[0]
        if holder == [] or not isinstance(holder[0], (Plain, Para)):
            holder.insert(0, Para([]))
        block = holder[0]
        inlines = block[0]
        inlines.insert(0, span)

def proofify(doc):
    sections = []
    for elt, path in pandoc.iter(doc, path=True):
        if isinstance(elt, Div) and "section" in elt[0][1]:
            section = elt
            attributes, blocks = section
            if len(blocks) >= 1 and isinstance(blocks[0], Header):
                header = blocks[0]
                level, attributes, inlines = header[:]
                identifier, classes, key_value_pairs = attributes
                if "proof" in classes:
                    sections.append(section)

    # TODO: non-justified part not working
    for section in sections:
        # Not perfect, but a marker anyway.
        attributes, blocks = section
        blacksquare = Math(InlineMath(), r"\;\; \blacksquare")
        justified_blacksquare = RawInline("latex", r"\hfill$\blacksquare$")
        justified = True
        if blocks == [] or not isinstance(blocks[-1], (Plain, Para)):
            blocks.append(Plain([]))
            justified = False
        last_block = blocks[-1]
        inlines = last_block[0]
        if justified:
            inlines.append(justified_blacksquare)
        else:
            inlines.append(blacksquare)


def transform_image_format(doc):
    for elt in pandoc.iter(doc):
        if isinstance(elt, Image):
            image = elt
            attr, inlines, target = image[:]
            url, title = target
            if pathlib.Path(url).suffix in [".tex", ".py"]:
                new_target = url + ".pdf"
                image[:] = attr, inlines, (new_target, title)

def solve_toc_nesting(doc): # fuck you LaTeX!
    "Add the 'bookmark' package to solve TOC issues"
    meta, blocks = doc[:]
    metamap = meta[0]
    metamap["header-includes"] = MetaList(
        [MetaBlocks([RawBlock(Format("tex"), "\\usepackage{bookmark}")])]
    )

def add_font_awesome(doc):
    meta, blocks = doc[:]
    metamap = meta[0]
    metalist = metamap["header-includes"]
    metablocks = metalist[0][0]
    metablocks[0].append(RawBlock(Format("tex"), "\\usepackage{fontawesome}"))

def add_marginnote(doc):
    meta, blocks = doc[:]
    metamap = meta[0]
    metalist = metamap["header-includes"]
    metablocks = metalist[0][0]
    metablocks[0].append(RawBlock(Format("tex"), "\\usepackage{marginnote}"))

def flag_definitions(doc):
    for elt in pandoc.iter(doc):
        if isinstance(elt, Header):
            header = elt
            level, attr, inlines = header[:]
            id_, classes, kv_pairs = attr
            if "definition" in classes:
                inlines = [RawInline(Format("tex"), r"\faFlagO\;\;")] + inlines # Space() doesn't seem to work :(
                header[:] = level, attr, inlines


# ------------------------------------------------------------------------------

# Files and Directories
root = pathlib.Path(".").resolve()
output = root / "output"
images = root / "images"
try:
    output.mkdir()
except FileExistsError:
    pass
bibliography = root / "bibliography.json"

# Documents
_docs = [path.stem for path in list(root.glob("*.md"))]
_docs = [doc for doc in _docs if not doc.startswith("_")]
if len(_docs) != 1:
    error = "cannot identify the main document "
    error += f"(found {len(docs)} markdown files)"
    raise RuntimeError(error)
doc = _docs[0]
doc_md = doc + ".md"
doc_tex = str(output / (doc + ".tex"))
doc_pdf = str(output / (doc + ".pdf"))
doc_odt = str(output / (doc + ".odt"))
doc_html = str(output / (doc + ".html"))
doc_md_md = str(output / (doc + ".md"))

# Images
if images.exists():
    try:
        os.chdir(images)
        l = pathlib.Path(".")
        for tex_file in l.glob("*.tex"):
            pdflatex(tex_file)
            pdf_file = tex_file.with_suffix(".pdf")
            # path.rename (which makes more sense) won't work with Windows
            # if the target file already exists while path.replace works
            # for all platforms (AFAICT).
            pdf_file.replace(tex_file.with_suffix(tex_file.suffix + ".pdf"))
        for python_file in l.glob("*.py"):
            python(python_file)
    finally:
        clean_latex_trash()
        os.chdir(root)

# Doctest
python("-m", "doctest", doc_md)

# Pandoc Options
options = ["--standalone"]
options += ["-V", "lang=fr"]
options += ["--table-of-contents"]
if bibliography.exists():
    options += ["--bibliography=bibliography.json", "-M", "link-citations=true"]
TEX_options = options.copy()
PDF_options = options.copy()
ODT_options = options.copy()
HTML_options = options.copy()
HTML_options += ["--mathjax"]

# PDF Output
doc = pandoc.read(file=doc_md)
doc = transform(doc)
pandoc.write(doc, file=doc_tex, options=TEX_options)
pandoc.write(doc, file=doc_pdf, options=PDF_options)
pandoc.write(doc, format="html5", file=doc_html, options=HTML_options)
pandoc.write(doc, format="odt", file=doc_odt, options=ODT_options)
