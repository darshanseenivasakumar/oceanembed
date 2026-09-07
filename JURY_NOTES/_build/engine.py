"""Jury-notes PDF engine.

Turns a list of content blocks into a styled A4 PDF. Presentation only -- it computes
no science. Every number that appears in a note is transcribed from PROJECT_RECORD.md,
docs/, artifacts/ or a commit message, and carries its own evidence tag in the text.

Fonts are Windows system TTFs so the documents can carry degC, sigma, +/- and arrows
without the box-glyph problem the built-in Type-1 fonts have.
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------- fonts

_F = r"C:\Windows\Fonts"


def _register() -> None:
    pairs = [
        ("SegoeUI", "segoeui.ttf"),
        ("SegoeUI-Bold", "segoeuib.ttf"),
        ("SegoeUI-Italic", "segoeuii.ttf"),
        ("SegoeUI-Light", "segoeuil.ttf"),
        ("Consolas", "consola.ttf"),
        ("Consolas-Bold", "consolab.ttf"),
        ("Georgia", "georgia.ttf"),
        ("Georgia-Italic", "georgiai.ttf"),
        ("Georgia-Bold", "georgiab.ttf"),
    ]
    for name, filename in pairs:
        path = os.path.join(_F, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"required font missing: {path}")
        pdfmetrics.registerFont(TTFont(name, path))
    pdfmetrics.registerFontFamily(
        "SegoeUI", normal="SegoeUI", bold="SegoeUI-Bold",
        italic="SegoeUI-Italic", boldItalic="SegoeUI-Bold",
    )
    pdfmetrics.registerFontFamily(
        "Georgia", normal="Georgia", bold="Georgia-Bold",
        italic="Georgia-Italic", boldItalic="Georgia-Bold",
    )
    pdfmetrics.registerFontFamily(
        "Consolas", normal="Consolas", bold="Consolas-Bold",
        italic="Consolas", boldItalic="Consolas-Bold",
    )


_register()

# ---------------------------------------------------------------- palette

NAVY = colors.HexColor("#0B3C5D")
DEEP = colors.HexColor("#08293E")
TEAL = colors.HexColor("#1D7874")
TEAL_L = colors.HexColor("#E4F1F0")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#5B6B7B")
RULE = colors.HexColor("#D3DCE4")
PANEL = colors.HexColor("#F2F6F9")
CODE_BG = colors.HexColor("#F4F6F8")
CODE_BAR = colors.HexColor("#0B3C5D")
AMBER = colors.HexColor("#B45309")
AMBER_L = colors.HexColor("#FDF3E3")
GREEN = colors.HexColor("#166534")
GREEN_L = colors.HexColor("#E9F5EC")
PLUM = colors.HexColor("#5B3A8E")
PLUM_L = colors.HexColor("#F1ECFA")
ZEBRA = colors.HexColor("#F7FAFC")
WHITE = colors.white

PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 17 * mm
T_MARGIN = 16 * mm
B_MARGIN = 16 * mm
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN

# ---------------------------------------------------------------- styles

S = {}
S["body"] = ParagraphStyle(
    "body", fontName="SegoeUI", fontSize=9.6, leading=14.4, textColor=SLATE,
    alignment=TA_JUSTIFY, spaceAfter=6,
)
S["lead"] = ParagraphStyle(
    "lead", parent=S["body"], fontSize=11, leading=16.5, textColor=DEEP, spaceAfter=9,
)
S["h1"] = ParagraphStyle(
    "h1", fontName="SegoeUI-Bold", fontSize=13.2, leading=16.5, textColor=NAVY,
    spaceBefore=4, spaceAfter=2,
)
S["h2"] = ParagraphStyle(
    "h2", fontName="SegoeUI-Bold", fontSize=10.6, leading=14, textColor=TEAL,
    spaceBefore=8, spaceAfter=3,
)
S["bullet"] = ParagraphStyle(
    "bullet", parent=S["body"], alignment=TA_LEFT, spaceAfter=3.5,
)
S["step"] = ParagraphStyle(
    "step", parent=S["body"], alignment=TA_LEFT, spaceAfter=4.5,
)
S["code"] = ParagraphStyle(
    "code", fontName="Consolas", fontSize=8.2, leading=12, textColor=DEEP,
)
S["code_label"] = ParagraphStyle(
    "code_label", fontName="SegoeUI-Bold", fontSize=7, leading=9,
    textColor=colors.HexColor("#7C8B99"),
)
S["callout_title"] = ParagraphStyle(
    "callout_title", fontName="SegoeUI-Bold", fontSize=8.6, leading=11.5,
)
S["callout_body"] = ParagraphStyle(
    "callout_body", fontName="SegoeUI", fontSize=9.2, leading=13.6, textColor=SLATE,
    alignment=TA_JUSTIFY,
)
S["quote"] = ParagraphStyle(
    "quote", fontName="Georgia-Italic", fontSize=10.2, leading=15.5,
    textColor=DEEP, alignment=TA_LEFT,
)
S["th"] = ParagraphStyle(
    "th", fontName="SegoeUI-Bold", fontSize=8.2, leading=10.8, textColor=WHITE,
)
S["td"] = ParagraphStyle(
    "td", fontName="SegoeUI", fontSize=8.4, leading=11.4, textColor=SLATE,
)
S["td_b"] = ParagraphStyle(
    "td_b", fontName="SegoeUI-Bold", fontSize=8.4, leading=11.4, textColor=DEEP,
)
S["kv_k"] = ParagraphStyle(
    "kv_k", fontName="SegoeUI-Bold", fontSize=7.6, leading=10, textColor=colors.HexColor("#8296A8"),
)
S["kv_v"] = ParagraphStyle(
    "kv_v", fontName="SegoeUI", fontSize=8.8, leading=12, textColor=DEEP,
)
S["cover_kicker"] = ParagraphStyle(
    "cover_kicker", fontName="SegoeUI-Bold", fontSize=8.4, leading=11,
    textColor=colors.HexColor("#8FC1D4"),
)
S["cover_title"] = ParagraphStyle(
    "cover_title", fontName="SegoeUI-Bold", fontSize=20, leading=24, textColor=WHITE,
)
S["cover_sub"] = ParagraphStyle(
    "cover_sub", fontName="SegoeUI-Light", fontSize=10.4, leading=15,
    textColor=colors.HexColor("#D6E6EF"),
)
S["badge"] = ParagraphStyle(
    "badge", fontName="SegoeUI-Bold", fontSize=24, leading=26,
    textColor=WHITE, alignment=TA_CENTER,
)
S["badge_sub"] = ParagraphStyle(
    "badge_sub", fontName="SegoeUI", fontSize=6.6, leading=8,
    textColor=colors.HexColor("#8FC1D4"), alignment=TA_CENTER,
)
S["foot"] = ParagraphStyle(
    "foot", fontName="SegoeUI", fontSize=7.4, leading=9, textColor=colors.HexColor("#8296A8"),
)

CALLOUT_KIND = {
    "note": (NAVY, colors.HexColor("#EDF3F8")),
    "good": (GREEN, GREEN_L),
    "warn": (AMBER, AMBER_L),
    "jury": (PLUM, PLUM_L),
    "teal": (TEAL, TEAL_L),
}

# ---------------------------------------------------------------- blocks


def _p(text, style="body"):
    return Paragraph(text, S[style])


def heading(text):
    """Section heading with a hairline under it."""
    t = Table(
        [[_p(text, "h1")], [""]],
        colWidths=[CONTENT_W], rowHeights=[None, 2],
    )
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("BOTTOMPADDING", (0, 1), (0, 1), 0),
        ("LINEBELOW", (0, 1), (0, 1), 0.8, TEAL),
    ]))
    return [Spacer(1, 7), t, Spacer(1, 5)]


def bullets(items, style="bullet"):
    return ListFlowable(
        [ListItem(_p(i, style), leftIndent=12, value="square") for i in items],
        bulletType="bullet", bulletFontName="SegoeUI", bulletFontSize=5.5,
        bulletColor=TEAL, leftIndent=11, bulletOffsetY=-2.5, spaceBefore=1, spaceAfter=4,
    )


def steps(items):
    """Numbered steps, each in a circle-free but clearly ordered list."""
    rows = []
    for n, item in enumerate(items, 1):
        num = Table([[_p(f"{n}", "badge_num")]], colWidths=[13], rowHeights=[13])
        num.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), TEAL),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        rows.append([num, _p(item, "step")])
    t = Table(rows, colWidths=[19, CONTENT_W - 19])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 0),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


S["badge_num"] = ParagraphStyle(
    "badge_num", fontName="SegoeUI-Bold", fontSize=8, leading=9.5,
    textColor=WHITE, alignment=TA_CENTER,
)


def cmd(lines, label="RUN THIS"):
    """A monospace command box with a coloured spine."""
    if isinstance(lines, str):
        lines = [lines]
    body = "<br/>".join(
        ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace(" ", "&nbsp;") for ln in lines
    )
    inner = [[_p(label, "code_label")], [_p(body, "code")]]
    t_in = Table(inner, colWidths=[CONTENT_W - 16])
    t_in.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 7),
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
    ]))
    t = Table([["", t_in]], colWidths=[3.2, CONTENT_W - 3.2])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CODE_BAR),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 7)])


def callout(title, text, kind="note"):
    fg, bg = CALLOUT_KIND[kind]
    title_style = ParagraphStyle("ct", parent=S["callout_title"], textColor=fg)
    rows = []
    if title:
        rows.append([Paragraph(title.upper(), title_style)])
    rows.append([_p(text, "callout_body")])
    inner = Table(rows, colWidths=[CONTENT_W - 20])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, -1), (0, -1), 7),
        ("TOPPADDING", (0, -1), (0, -1), 2 if title else 6),
        ("BACKGROUND", (0, 0), (-1, -1), bg),
    ]))
    t = Table([["", inner]], colWidths=[3.2, CONTENT_W - 3.2])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), fg),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 7)])


def quote(text, attrib=None):
    rows = [[_p(text, "quote")]]
    if attrib:
        rows.append([_p(attrib, "kv_k")])
    inner = Table(rows, colWidths=[CONTENT_W - 22])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, -1), (0, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), PLUM_L),
    ]))
    t = Table([["", inner]], colWidths=[3.6, CONTENT_W - 3.6])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), PLUM),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


def table(rows, widths=None, align=None, bold_col0=False, font_size=None):
    """rows[0] is the header. widths are fractions of the content width."""
    ncol = len(rows[0])
    if widths is None:
        widths = [1.0 / ncol] * ncol
    total = sum(widths)
    colw = [CONTENT_W * w / total for w in widths]

    td = S["td"]
    tdb = S["td_b"]
    if font_size:
        td = ParagraphStyle("td_s", parent=S["td"], fontSize=font_size, leading=font_size + 3)
        tdb = ParagraphStyle("tdb_s", parent=S["td_b"], fontSize=font_size, leading=font_size + 3)

    data = [[Paragraph(str(c), S["th"]) for c in rows[0]]]
    for r in rows[1:]:
        data.append([
            Paragraph(str(c), tdb if (bold_col0 and i == 0) else td)
            for i, c in enumerate(r)
        ])

    t = Table(data, colWidths=colw, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    if align:
        for i, a in enumerate(align):
            style.append(("ALIGN", (i, 0), (i, -1), a))
    t.setStyle(TableStyle(style))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 8)])


def kvstrip(pairs):
    """A compact metadata strip: 2-4 label/value cells across."""
    cells = []
    for k, v in pairs:
        inner = Table([[_p(k.upper(), "kv_k")], [_p(v, "kv_v")]])
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (0, 0), 0),
            ("BOTTOMPADDING", (0, 0), (0, 0), 1.5),
            ("TOPPADDING", (0, 1), (0, 1), 0),
            ("BOTTOMPADDING", (0, 1), (0, 1), 0),
        ]))
        cells.append(inner)
    n = len(cells)
    w = CONTENT_W / n
    t = Table([cells], colWidths=[w] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.6, RULE),
    ]))
    return KeepTogether([t, Spacer(1, 9)])


S["tile_v"] = ParagraphStyle(
    "tile_v", fontName="SegoeUI-Bold", fontSize=15, leading=18,
    textColor=WHITE, alignment=TA_CENTER,
)
S["tile_k"] = ParagraphStyle(
    "tile_k", fontName="SegoeUI", fontSize=7.2, leading=9.5,
    textColor=colors.HexColor("#A9CBDB"), alignment=TA_CENTER,
)


def stat_tiles(tiles):
    """Three or four (value, label) tiles on the dark ground."""
    cells = []
    for value, label in tiles:
        inner = Table([[_p(value, "tile_v")], [_p(label.upper(), "tile_k")]])
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (0, 0), 0),
            ("BOTTOMPADDING", (0, 0), (0, 0), 2),
            ("TOPPADDING", (0, 1), (0, 1), 0),
            ("BOTTOMPADDING", (0, 1), (0, 1), 0),
        ]))
        cells.append(inner)
    n = len(cells)
    t = Table([cells], colWidths=[CONTENT_W / n] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), DEEP),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.7, colors.HexColor("#1D4E6B")),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 7)])


def recap(text, tiles, tail=None):
    """The closing card: one-line recap, three numbers, and a pointer onward."""
    out = [Spacer(1, 9)]
    head = Table([[_p("IN ONE LINE", "code_label")], [_p(text, "quote")]],
                 colWidths=[CONTENT_W - 22])
    head.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 0), (0, 0), 1),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_L),
    ]))
    spine = Table([["", head]], colWidths=[3.6, CONTENT_W - 3.6])
    spine.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    out.append(spine)
    out.append(stat_tiles(tiles))
    if tail:
        out.append(_p(tail, "kv_k"))
    return out


def cover(badge, badge_sub, kicker, title, subtitle):
    """The dark title block at the top of page 1."""
    b = Table([[_p(badge, "badge")], [_p(badge_sub, "badge_sub")]], colWidths=[46])
    b.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (0, 0), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 1), (0, 1), 1),
        ("BOTTOMPADDING", (0, 1), (0, 1), 4),
        ("BACKGROUND", (0, 0), (-1, -1), TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    right = Table([
        [_p(kicker, "cover_kicker")],
        [_p(title, "cover_title")],
        [_p(subtitle, "cover_sub")],
    ], colWidths=[CONTENT_W - 46 - 26])
    right.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 5),
        ("TOPPADDING", (0, 2), (0, 2), 0),
        ("BOTTOMPADDING", (0, 2), (0, 2), 0),
    ]))

    t = Table([[b, right]], colWidths=[46 + 14, CONTENT_W - 46 - 14])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), DEEP),
        ("LEFTPADDING", (0, 0), (0, 0), 14),
        ("RIGHTPADDING", (0, 0), (0, 0), 14),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    return [t, Spacer(1, 11)]


# ---------------------------------------------------------------- document


class _Doc(BaseDocTemplate):
    def __init__(self, path, footer_left, **kw):
        super().__init__(
            path, pagesize=A4,
            leftMargin=L_MARGIN, rightMargin=R_MARGIN,
            topMargin=T_MARGIN, bottomMargin=B_MARGIN,
            title=kw.pop("doc_title", footer_left),
            author="OceanEmbed / Team SIH26066",
            subject="SIH 2026 problem statement SIH26066 - jury briefing note",
            creator="OceanEmbed JURY_NOTES builder",
        )
        self.footer_left = footer_left
        frame = Frame(
            L_MARGIN, B_MARGIN, CONTENT_W,
            PAGE_H - T_MARGIN - B_MARGIN, id="main",
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self._decorate)])

    def _decorate(self, canv, doc):
        canv.saveState()
        y = B_MARGIN - 7 * mm
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.6)
        canv.line(L_MARGIN, y + 9, PAGE_W - R_MARGIN, y + 9)
        canv.setFont("SegoeUI", 7.4)
        canv.setFillColor(colors.HexColor("#8296A8"))
        canv.drawString(L_MARGIN, y, self.footer_left)
        canv.drawRightString(PAGE_W - R_MARGIN, y, f"Page {doc.page}")
        canv.restoreState()


def build(path, footer_left, story, doc_title=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _Doc(path, footer_left, doc_title=doc_title or footer_left).build(list(story))
    return path


__all__ = [
    "heading", "bullets", "steps", "cmd", "callout", "quote", "table",
    "kvstrip", "cover", "build", "Spacer", "PageBreak", "_p",
    "stat_tiles", "recap",
]
