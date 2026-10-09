#!/usr/bin/env python3
"""Render this manuscript's supported LaTeX content as a reviewed PDF reading copy.

This is a ReportLab renderer, not a TeX compiler. Unsupported TeX constructs fail
explicitly. The saved TeX source remains the editable manuscript of record.
"""

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties
from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                               NextPageTemplate, PageBreak, PageTemplate,
                               Paragraph, Spacer, Table, TableStyle)


def group(text, start):
    if text[start] != "{":
        raise ValueError("Expected a LaTeX brace group")
    depth = 1
    for index in range(start + 1, len(text)):
        if text[index] in "{}" and text[index - 1] != "\\":
            depth += 1 if text[index] == "{" else -1
            if depth == 0:
                return text[start + 1:index], index + 1
    raise ValueError("Unclosed LaTeX group")


def command_value(text, command):
    match = re.search(r"\\" + re.escape(command) + r"\s*\{", text)
    if not match:
        return None
    return group(text, match.end() - 1)[0]


class Renderer:
    def __init__(self, source, output, temporary, draft):
        self.source, self.output, self.temporary, self.draft = source, output, temporary, draft
        self.temporary.mkdir(parents=True, exist_ok=True)
        self.width = A4[0] - 44 * mm
        self.flow, self.math_count, self.table_count, self.figure_count = [], 0, 0, 0
        self.references = {}
        self.fonts()
        self.styles = {
            "body": ParagraphStyle("Body", fontName="DejaVuSerif", fontSize=10.2, leading=14.3,
                                   spaceAfter=6.5, alignment=TA_LEFT, allowWidows=0, allowOrphans=0),
            "title": ParagraphStyle("Title", fontName="DejaVuSerif-Bold", fontSize=17, leading=21,
                                    spaceAfter=11),
            "author": ParagraphStyle("Author", fontName="DejaVuSerif", fontSize=10.5, leading=14, spaceAfter=15),
            "section": ParagraphStyle("Section", fontName="DejaVuSerif-Bold", fontSize=12.2, leading=16,
                                      spaceBefore=13, spaceAfter=7, keepWithNext=True),
            "subsection": ParagraphStyle("Subsection", fontName="DejaVuSerif-Bold", fontSize=10.5, leading=14.4,
                                         spaceBefore=9, spaceAfter=5, keepWithNext=True),
            "caption": ParagraphStyle("Caption", fontName="DejaVuSerif", fontSize=9, leading=12, spaceAfter=7),
            "cell": ParagraphStyle("Cell", fontName="DejaVuSerif", fontSize=8.2, leading=10.5),
            "reference": ParagraphStyle("Reference", fontName="DejaVuSerif", fontSize=8.5, leading=11.5,
                                        leftIndent=14, firstLineIndent=-14, spaceAfter=6),
        }

    @staticmethod
    def fonts():
        folder = Path(matplotlib.get_data_path()) / "fonts/ttf"
        for name in ("DejaVuSerif", "DejaVuSerif-Bold", "DejaVuSerif-Italic", "DejaVuSerif-BoldItalic"):
            pdfmetrics.registerFont(TTFont(name, str(folder / (name + ".ttf"))))
        pdfmetrics.registerFontFamily("DejaVuSerif", normal="DejaVuSerif", bold="DejaVuSerif-Bold",
                                      italic="DejaVuSerif-Italic", boldItalic="DejaVuSerif-BoldItalic")

    def math_image(self, expression, block=False):
        expression = " ".join(expression.split())
        if re.search(r"(?:PERCENT|AMPERSAND|UNDERSCORE|HASH|XML)TOKEN", expression):
            raise ValueError("Internal text escape token reached math rendering")
        key = hashlib.sha256((str(block) + expression).encode()).hexdigest()[:20]
        path = self.temporary / ("math_" + key + ".png")
        if not path.exists():
            mathtext.math_to_image("$" + expression + "$", path,
                                  prop=FontProperties(family="DejaVu Serif", size=12 if block else 10.2),
                                  dpi=240, format="png", color="#111111")
        with PILImage.open(path) as im:
            width, height = im.size
        self.math_count += 1
        return path, width * 72 / 240, height * 72 / 240

    def inline(self, text):
        text = text.replace("\\noindent", "").replace("\\centering", "")
        for name, value in (("gd", "γδ"), ("gtd", "γ→δ"), ("dtg", "δ→γ")):
            text = re.sub(r"\\" + name + r"(?:\{\})?(?![A-Za-z])", lambda _: value, text)
        text = text.replace("\\ ", " ").replace("~", " ").replace("---", "-").replace("--", "-")
        text = text.replace('\\"o', "ö").replace("``", '"').replace("''", '"')
        tokens = {}

        def mask(value):
            name = f"XMLTOKEN{len(tokens):05d}TOKEN"
            tokens[name] = value
            return name

        def math_replace(match):
            path, width, height = self.math_image(match.group(1))
            return mask(f'<img src="{html.escape(str(path.resolve()), quote=True)}" width="{width:.3f}" height="{height:.3f}" valign="-2"/>')

        text = re.sub(r"\$(.+?)\$", math_replace, text, flags=re.S)
        # Mathtext must receive the original TeX escapes (especially \%).
        # Protect literal text characters only after math expressions are masked.
        text = text.replace("\\%", "PERCENTTOKEN").replace("\\&", "AMPERSANDTOKEN")
        text = text.replace("\\_", "UNDERSCORETOKEN").replace("\\#", "HASHTOKEN")
        text = re.sub(r"\\cite\{([^}]+)\}", lambda m: "[" + ", ".join(str(self.references[k.strip()]) for k in m.group(1).split(",")) + "]", text)
        text = re.sub(r"\\ref\{([^}]+)\}", lambda m: self.labels[m.group(1)], text)
        for command, tag in (("textbf", "b"), ("textit", "i"), ("emph", "i")):
            while (match := re.search(r"\\" + command + r"\s*\{", text)) is not None:
                content, end = group(text, match.end() - 1)
                value = mask("<" + tag + ">" + self.inline(content) + "</" + tag + ">")
                text = text[:match.start()] + value + text[end:]
        text = text.replace("PERCENTTOKEN", "%").replace("AMPERSANDTOKEN", "&")
        text = text.replace("UNDERSCORETOKEN", "_").replace("HASHTOKEN", "#")
        text = text.replace("{", "").replace("}", "")
        if re.search(r"\\[A-Za-z]+", text):
            raise ValueError("Unsupported inline LaTeX: " + text[:250])
        text = " ".join(text.split())
        text = html.escape(text)
        for name, value in reversed(list(tokens.items())):
            text = text.replace(name, value)
        return text

    def paragraphs(self, text):
        # These exact commands only reset supplementary figure numbering. The
        # labels below carry the same S1/S2 values in this reading-copy renderer.
        text = text.replace(r"\setcounter{figure}{0}", "")
        text = text.replace(r"\renewcommand{\thefigure}{S\arabic{figure}}", "")
        pattern = re.compile(r"\\(section\*?|subsection\*?|subsubsection\*?)\s*\{")
        while (match := pattern.search(text)) is not None:
            self.paragraphs(text[:match.start()])
            title, end = group(text, match.end() - 1)
            style = "section" if match.group(1).startswith("section") else "subsection"
            self.flow.append(Paragraph(self.inline(title), self.styles[style]))
            text = text[end:]
        text = text.replace("\\maketitle", "").replace("\\clearpage", "").replace("\\newpage", "")
        text = re.sub(r"\\label\{[^}]+\}", "", text)
        for paragraph in re.split(r"\n\s*\n", text):
            if paragraph.strip():
                self.flow.append(Paragraph(self.inline(paragraph), self.styles["body"]))

    def table(self, body):
        self.table_count += 1
        caption = command_value(body, "caption") or ""
        match = re.search(r"\\begin\{tabular\}\s*\{", body)
        if not match:
            raise ValueError("Unsupported table structure")
        _, start = group(body, match.end() - 1)
        end = body.index(r"\end{tabular}", start)
        contents = re.sub(r"\\(?:toprule|midrule|bottomrule|hline)", "", body[start:end])
        rows = [re.split(r"(?<!\\)&", row.strip()) for row in re.split(r"\\\\\s*", contents) if row.strip()]
        require_columns = len(rows[0])
        if any(len(row) != require_columns for row in rows):
            raise ValueError("Table column count differs")
        first = .22 if require_columns >= 6 else .42 if require_columns > 2 else .62
        widths = [self.width * first] + [self.width * (1 - first) / (require_columns - 1)] * (require_columns - 1)
        data = [[Paragraph(("<b>" if i == 0 else "") + self.inline(value) + ("</b>" if i == 0 else ""), self.styles["cell"])
                 for value in row] for i, row in enumerate(rows)]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LINEABOVE", (0, 0), (-1, 0), .7, colors.black),
                                   ("LINEBELOW", (0, 0), (-1, 0), .4, colors.black),
                                   ("LINEBELOW", (0, -1), (-1, -1), .7, colors.black),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        caption_flow = Paragraph(f"<b>Table {self.table_count}.</b> " + self.inline(caption), self.styles["caption"])
        if len(rows) <= 18:
            self.flow.append(KeepTogether([caption_flow, table]))
        else:
            self.flow.extend((caption_flow, table))
        self.flow.append(Spacer(1, 9))

    def figure(self, body):
        caption = command_value(body, "caption") or ""
        label = command_value(body, "label")
        match = re.search(r"\\includegraphics(?:\[[^]]*\])?\s*\{([^}]+)\}", body)
        if not match:
            raise ValueError("Figure requires an explicit saved image")
        path = self.source.parent / match.group(1)
        if path.suffix == ".pdf" and path.with_suffix(".png").exists():
            path = path.with_suffix(".png")
        with PILImage.open(path) as image:
            width, height = image.size
        maximum_width, maximum_height = landscape(A4)[0] - 38 * mm, landscape(A4)[1] - 60 * mm
        scale = min(maximum_width / width, maximum_height / height)
        if len(self.flow) >= 2 and isinstance(self.flow[-1], PageBreak) and isinstance(self.flow[-2], NextPageTemplate):
            self.flow = self.flow[:-2]
        self.flow.extend((NextPageTemplate("figure"), PageBreak()))
        self.flow.append(Image(str(path), width=width * scale, height=height * scale, hAlign="CENTER"))
        number = self.labels.get(label, str(self.figure_count + 1))
        self.flow.append(Spacer(1, 8))
        self.flow.append(Paragraph("<b>Figure " + number + ".</b> " + self.inline(caption), self.styles["caption"]))
        self.flow.extend((NextPageTemplate("body"), PageBreak()))
        self.figure_count += 1

    def parse(self, text):
        # Remove only actual TeX comments, preserving escaped percentages.
        text = re.sub(r"(?<!\\)%[^\n]*", "", text)
        title = command_value(text, "title")
        author = command_value(text, "author")
        self.references = {key: i + 1 for i, key in enumerate(re.findall(r"\\bibitem\{([^}]+)\}", text))}
        self.labels = {}
        for kind in ("figure", "table"):
            index = 0
            for match in re.finditer(r"\\begin\{" + kind + r"\}(.*?)\\end\{" + kind + r"\}", text, re.S):
                index += 1
                label = command_value(match.group(1), "label")
                if label:
                    self.labels[label] = "S" + label.rsplit("S", 1)[-1].split("_")[0] if "_S" in label else str(index)
        self.flow.append(Paragraph(self.inline(title), self.styles["title"]))
        self.flow.append(Paragraph(self.inline(author), self.styles["author"]))
        if self.draft:
            self.flow.append(Paragraph("<b>Working manuscript - model results incomplete.</b>", self.styles["caption"]))
        body = text.split("\\begin{document}", 1)[1].rsplit("\\end{document}", 1)[0]
        pattern = re.compile(r"\\begin\{(abstract|table|equation|figure|thebibliography)\}(?:\[[^]]*\])?(?:\{99\})?")
        while (match := pattern.search(body)) is not None:
            self.paragraphs(body[:match.start()])
            kind = match.group(1)
            end = body.index("\\end{" + kind + "}", match.end())
            content = body[match.end():end]
            if kind == "abstract":
                self.flow.append(Paragraph("Abstract", self.styles["section"]))
                self.paragraphs(content)
            elif kind == "table":
                self.table(content)
            elif kind == "figure":
                self.figure(content)
            elif kind == "equation":
                path, width, height = self.math_image(content, block=True)
                scale = min(1., self.width / width)
                self.flow.extend((Spacer(1, 4), Image(str(path), width=width * scale, height=height * scale), Spacer(1, 10)))
            else:
                self.flow.append(Paragraph("References", self.styles["section"]))
                refs = re.split(r"\\bibitem\{([^}]+)\}", content)
                for i in range(1, len(refs), 2):
                    key, value = refs[i:i + 2]
                    self.flow.append(Paragraph(str(self.references[key]) + ". " + self.inline(value), self.styles["reference"]))
            body = body[end + len("\\end{" + kind + "}"):]
        self.paragraphs(body)
        return title

    def footer(self, canvas, document):
        canvas.saveState()
        width, height = canvas._pagesize
        canvas.setFont("DejaVuSerif", 7.4)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(20 * mm, 13 * mm, "Anonymous working manuscript" if self.draft else "Anonymous manuscript")
        canvas.drawRightString(width - 20 * mm, 13 * mm, str(document.page))
        canvas.restoreState()

    def build(self, title):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        document = BaseDocTemplate(str(self.output), pagesize=A4, title=title, author="Anonymous",
                                   subject="Recorded human gamma-delta TCR partner recovery",
                                   leftMargin=22 * mm, rightMargin=22 * mm, topMargin=21 * mm, bottomMargin=21 * mm)
        body = Frame(22 * mm, 21 * mm, self.width, A4[1] - 42 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        size = landscape(A4)
        figure = Frame(19 * mm, 20 * mm, size[0] - 38 * mm, size[1] - 38 * mm,
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        document.addPageTemplates([PageTemplate(id="body", frames=[body], pagesize=A4, onPage=self.footer),
                                   PageTemplate(id="figure", frames=[figure], pagesize=size, onPage=self.footer)])
        # Avoid a trailing empty page after a final figure.
        if self.flow and isinstance(self.flow[-1], PageBreak):
            self.flow.pop()
        document.build(self.flow)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temporary", type=Path, default=Path("tmp/pdfs/manuscript_math"))
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    text = args.source.read_text()
    if not args.allow_draft and re.search(r"working manuscript|Working-results section|final model-level conclusion|not yet incorporated", text, re.I):
        raise ValueError("Incomplete scientific text cannot be exported as the final manuscript")
    renderer = Renderer(args.source, args.output, args.temporary, args.allow_draft)
    title = renderer.parse(text)
    renderer.build(title)
    pdf = PdfReader(str(args.output))
    extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
    if not extracted.strip() or any(s in extracted for s in ("/gpfs/", "zihanhe25", "jiameng_mres")):
        raise ValueError("PDF text missing or contains local identity metadata")
    if len(re.findall(r"\bReferences\b", extracted)) != 1:
        raise ValueError("Reference section missing or duplicated")
    report = {"source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "pdf_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
              "renderer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "renderer": "ReportLab reading copy, not native TeX compilation", "draft": args.allow_draft,
              "pages": len(pdf.pages), "figures": renderer.figure_count, "tables": renderer.table_count,
              "references": len(renderer.references), "math_occurrences": renderer.math_count,
              "text_characters": len(extracted), "visual_inspection_required": True}
    args.output.with_suffix(".render.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(".txt").write_text(extracted + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
