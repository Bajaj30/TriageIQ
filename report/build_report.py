"""Builds report/TriageIQ_Project_Report.pdf — the academic project report.

Every number is copied from Context/FACTS.md, NLP.md, training/results/*.json or CLAUDE.md (the measured tables).
Figures are drawn here with matplotlib; the PDF is laid out with reportlab.

Run:  python report/build_report.py      (needs reportlab + matplotlib)
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate
from reportlab.platypus.frames import Frame
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
OUT = HERE / "TriageIQ_Project_Report.pdf"

# ---------------------------------------------------------------- fonts (Liberation Serif + DejaVu: both have →, ≈, ×, ≤ …)
D, L = "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/"
for name, file in [("Serif", L + "LiberationSerif-Regular.ttf"), ("Serif-B", L + "LiberationSerif-Bold.ttf"),
                   ("Serif-I", L + "LiberationSerif-Italic.ttf"), ("Sans", D + "DejaVuSans.ttf"),
                   ("Sans-B", D + "DejaVuSans-Bold.ttf"), ("Mono", D + "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, file))
pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-B", italic="Serif-I", boldItalic="Serif-B")
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans", boldItalic="Sans-B")

INK, ACCENT, MUTED, RULE = colors.HexColor("#1b1b1b"), colors.HexColor("#7a1f2b"), colors.HexColor("#555555"), colors.HexColor("#bbbbbb")
BODY = ParagraphStyle("body", fontName="Serif", fontSize=10.8, leading=14.6, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=5)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, bulletIndent=4, spaceAfter=2.5)
H1 = ParagraphStyle("h1", fontName="Sans-B", fontSize=16, leading=20, textColor=ACCENT, spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("h2", fontName="Sans-B", fontSize=12, leading=15, textColor=INK, spaceBefore=9, spaceAfter=5)
H3 = ParagraphStyle("h3", fontName="Sans-B", fontSize=10.3, leading=13, textColor=MUTED, spaceBefore=6, spaceAfter=3)
CAP = ParagraphStyle("cap", fontName="Serif-I", fontSize=8.8, leading=11, alignment=TA_CENTER, textColor=MUTED, spaceAfter=10)
CELL = ParagraphStyle("cell", fontName="Serif", fontSize=8.4, leading=10.6, textColor=INK)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Sans-B", fontSize=8.2)
CODE = ParagraphStyle("code", fontName="Mono", fontSize=7.2, leading=9.8, textColor=INK, leftIndent=10,
                      backColor=colors.HexColor("#f3f1ec"), borderPadding=6, spaceBefore=4, spaceAfter=10)

story = []
fig_no, tab_no = [0], [0]


def p(t): story.append(Paragraph(t, BODY))
def h1(t):
    story.append(PageBreak()); story.append(Paragraph(t, H1))
def h2(t): story.append(Paragraph(t, H2))
def h3(t): story.append(Paragraph(t, H3))
def bullets(items):
    for it in items: story.append(Paragraph(it, BUL, bulletText="•"))
    story.append(Spacer(1, 4))
def code(t): story.append(Paragraph(t.replace("\n", "<br/>").replace(" ", "&nbsp;"), CODE))


def table(rows, widths, caption, bold_last=False, heading=None):
    tab_no[0] += 1
    data = [[Paragraph(str(c), CELLB if r == 0 else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    st = [("LINEABOVE", (0, 0), (-1, 0), 0.9, INK), ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
          ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f1ec")),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    for r in range(2, len(rows), 2):
        st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#fafaf7")))
    if bold_last:
        st.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f6e9ea")))
    t.setStyle(TableStyle(st))
    story.append(KeepTogether(([Paragraph(heading, H2)] if heading else []) + [Paragraph(f"Table {tab_no[0]}. {caption}", CAP), t, Spacer(1, 10)]))


def figure(path, width_cm, caption):
    fig_no[0] += 1
    w, h = plt.imread(path).shape[1], plt.imread(path).shape[0]
    img = Image(str(path), width=width_cm * cm, height=width_cm * cm * h / w)
    story.append(KeepTogether([img, Paragraph(f"Figure {fig_no[0]}. {caption}", CAP)]))


# ---------------------------------------------------------------- figures
def box(ax, x, y, w, h, text, fc="#ffffff", ec="#1b1b1b", fs=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, family="DejaVu Sans",
            weight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, label=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", lw=1, color="#333333"))
    if label:
        ax.text((x1 + x2) / 2 + 0.08, (y1 + y2) / 2, label, fontsize=7, color="#555555", family="DejaVu Sans")


def fig_system():
    fig, ax = plt.subplots(figsize=(10, 6.2)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.2); ax.axis("off")
    sand, rose, blue = "#f3f1ec", "#f6e9ea", "#e8eef5"
    ax.text(0.1, 5.95, "OFFLINE (MacBook M4 + Kaggle T4)", fontsize=9, weight="bold", color="#7a1f2b")
    box(ax, 0.1, 4.9, 2.2, 0.8, "CFPB CSV\n9.2 GB · 4.8 M complaints\n(2022–2024)", sand)
    box(ax, 2.8, 4.9, 2.4, 0.8, "PostgreSQL 16 (Docker)\nsnowflake schema · 16 GB\nfact + 6 dims + events", sand)
    box(ax, 5.7, 4.9, 2.0, 0.8, "SQL features\nmv_features → v_model_input\n(19 inputs, point-in-time)", sand)
    box(ax, 8.1, 4.9, 1.8, 0.8, "training set v3\nParquet + manifest\n292,940 rows", sand)
    arrow(ax, 2.3, 5.3, 2.8, 5.3); arrow(ax, 5.2, 5.3, 5.7, 5.3); arrow(ax, 7.7, 5.3, 8.1, 5.3)
    box(ax, 8.1, 3.6, 1.8, 0.85, "DistilBERT fusion\nfine-tune (3 epochs,\n~481 s/epoch, T4)", rose)
    arrow(ax, 9.0, 4.9, 9.0, 4.45)
    box(ax, 5.4, 3.6, 2.3, 0.85, "Platt calibration\n+ ONNX export (266 MB)\n+ XAI split (reader/judge)", rose)
    arrow(ax, 8.1, 4.02, 7.7, 4.02)
    box(ax, 2.8, 3.6, 2.2, 0.85, "serving schema\nsnapshot as of 2025-01-01\npg_dump 57 MB", sand)
    arrow(ax, 4.0, 4.9, 4.0, 4.45, "06_serving")
    ax.plot([0.1, 9.9], [3.3, 3.3], ls="--", color="#999999", lw=0.8)
    ax.text(0.1, 3.05, "ONLINE (Vercel + AWS EC2 t4g.small, Sydney)", fontsize=9, weight="bold", color="#7a1f2b")
    box(ax, 0.1, 1.7, 1.6, 0.8, "visitor\n(browser)", blue)
    box(ax, 2.1, 1.7, 1.9, 0.8, "Vercel static site\nHTML/CSS/JS\nadds secret header", blue)
    box(ax, 4.4, 1.7, 1.7, 0.8, "NGINX\n403 w/o secret\n5 req/s per visitor", blue)
    box(ax, 6.5, 1.7, 1.7, 0.8, "FastAPI (uvicorn)\n/predict /complaint\n/explain (job queue)", blue)
    box(ax, 8.5, 2.2, 1.4, 0.6, "ONNX Runtime\nCPU", rose, fs=7.5)
    box(ax, 8.5, 1.3, 1.4, 0.6, "Postgres\nserving schema", sand, fs=7.5)
    arrow(ax, 1.7, 2.1, 2.1, 2.1); arrow(ax, 4.0, 2.1, 4.4, 2.1); arrow(ax, 6.1, 2.1, 6.5, 2.1)
    arrow(ax, 8.2, 2.3, 8.5, 2.5); arrow(ax, 8.2, 1.9, 8.5, 1.6)
    arrow(ax, 6.6, 3.6, 7.6, 2.8, "model bundle"); arrow(ax, 3.9, 3.6, 8.9, 1.9, "restore dump")
    box(ax, 0.1, 0.25, 9.8, 0.75, "response:  P(monetary relief)  →  route = senior analyst if p ≥ 3.67 % (riskiest 10 %), else template reply"
        "\n+ optional \"Why this score?\" (Shapley values, queued, one at a time)", "#ffffff", fs=8.5)
    arrow(ax, 7.35, 1.7, 7.35, 1.0)
    fig.tight_layout(); fig.savefig(FIG / "system.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def fig_distilbert():
    fig, ax = plt.subplots(figsize=(10, 6.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.6); ax.axis("off")
    sand, rose = "#f3f1ec", "#f6e9ea"
    box(ax, 0.2, 0.2, 4.0, 0.7, "input:  [CLS]  tok₁ … tok₅₁₀  [SEP]  ([PAD] …)\n+ attention mask (1 = real, 0 = padding)", "#ffffff", fs=8)
    box(ax, 0.2, 1.2, 4.0, 0.8, "Embeddings: word-piece (30,524 × 768, incl. [DATE], [REDACTED])\n+ learned position (512 × 768)\n→ LayerNorm → dropout 0.1", sand, fs=7.8)
    arrow(ax, 2.2, 0.9, 2.2, 1.2)
    box(ax, 0.2, 2.3, 4.0, 2.7, "", "#ffffff")
    ax.text(2.2, 4.8, "Transformer block  × 6", ha="center", fontsize=9, weight="bold")
    box(ax, 0.45, 2.5, 3.5, 0.95, "Multi-head self-attention\n12 heads × 64 dims · softmax(QKᵀ/√64)·V\nout proj 768→768 · residual + LayerNorm", rose, fs=7.6)
    box(ax, 0.45, 3.85, 3.5, 0.75, "Position-wise feed-forward\nLinear 768→3072 · GELU · Linear 3072→768\ndropout 0.1 · residual + LayerNorm", rose, fs=7.6)
    arrow(ax, 2.2, 2.0, 2.2, 2.5); arrow(ax, 2.2, 3.45, 2.2, 3.85)
    box(ax, 0.2, 5.35, 4.0, 0.8, "last_hidden_state: 768 numbers per piece\ntake position 0 = [CLS] vector (768)", sand, fs=8)
    arrow(ax, 2.2, 5.0, 2.2, 5.35)
    # right panel: facts
    facts = ("DistilBERT-base-uncased (Sanh et al., 2019)\n\n"
             "• student of BERT-base: 6 layers instead of 12\n"
             "• hidden 768 · 12 heads · FFN 3,072 · GELU\n"
             "• max 512 positions · WordPiece vocab 30,522\n"
             "• no token-type embeddings, no pooler, no NSP\n"
             "• initialised from every 2nd layer of BERT\n"
             "• pre-trained on BookCorpus + English Wikipedia\n"
             "  loss = distillation (soft targets, temperature)\n"
             "       + masked-LM + cosine (hidden-state) loss\n"
             "• ≈ 66 M parameters; 40 % smaller, 60 % faster,\n"
             "  ~97 % of BERT's GLUE score (authors)\n\n"
             "In TriageIQ: 2 special tokens added and the\n"
             "embedding table resized 30,522 → 30,524;\n"
             "encoder ≈ 66.36 M parameters, fine-tuned end-to-end\n"
             "(frozen in epoch 1, lr 2e-5 in epochs 2–3).")
    ax.text(4.7, 6.2, facts, va="top", fontsize=8.3, family="DejaVu Sans",
            bbox=dict(boxstyle="round,pad=0.5", fc="#fafaf7", ec="#bbbbbb"))
    fig.tight_layout(); fig.savefig(FIG / "distilbert.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def fig_fusion():
    fig, ax = plt.subplots(figsize=(10, 5.6)); ax.set_xlim(0, 10); ax.set_ylim(0, 5.6); ax.axis("off")
    sand, rose, blue = "#f3f1ec", "#f6e9ea", "#e8eef5"
    box(ax, 0.1, 4.6, 3.0, 0.8, "complaint text\n→ clean_narrative() (SQL)\n→ WordPiece, ≤ 512 pieces", "#ffffff", fs=8)
    box(ax, 0.1, 3.4, 3.0, 0.85, "DistilBERT encoder (Figure 1)\n6 layers · 768 hidden\n[CLS] vector: 768", rose, fs=8)
    box(ax, 0.1, 2.1, 3.0, 0.9, "text branch\nLinear 768→128 · GELU · Dropout 0.1\n→ 128", rose, fs=8)
    arrow(ax, 1.6, 4.6, 1.6, 4.25); arrow(ax, 1.6, 3.4, 1.6, 3.0)
    box(ax, 3.6, 4.6, 3.1, 0.8, "19 SQL inputs from serving.model_input()\n4 categorical ids + 15 numbers/flags", "#ffffff", fs=8)
    box(ax, 3.6, 3.4, 1.5, 0.85, "entity embeddings\nproduct 4 · sub-prod 8\nissue 12 · state 8\n= 32", sand, fs=7.3)
    box(ax, 5.2, 3.4, 1.5, 0.85, "15 numerics\nlog1p(quiet days)\nstandardised\n(train mean/std)", sand, fs=7.3)
    arrow(ax, 4.35, 4.6, 4.35, 4.25); arrow(ax, 5.95, 4.6, 5.95, 4.25)
    box(ax, 3.6, 2.1, 3.1, 0.9, "table branch  (concat 32 + 15 = 47)\nLinear 47→128 · GELU · Dropout 0.1\nLinear 128→64 · GELU  → 64", sand, fs=7.8)
    arrow(ax, 4.35, 3.4, 4.6, 3.0); arrow(ax, 5.95, 3.4, 5.7, 3.0)
    box(ax, 1.8, 0.85, 4.0, 0.9, "fusion head  (concat 128 + 64 = 192)\nLinear 192→64 · GELU · Dropout 0.1 · Linear 64→1\n→ logit", blue, fs=8)
    arrow(ax, 1.6, 2.1, 3.0, 1.75); arrow(ax, 5.15, 2.1, 4.6, 1.75)
    box(ax, 7.2, 0.85, 2.7, 0.9, "z = logit − 2.4165 (prior)\np = σ(0.7025·z − 0.7621)\nsenior if p ≥ 0.0367", "#ffffff", fs=8)
    arrow(ax, 5.8, 1.3, 7.2, 1.3)
    ax.text(7.25, 4.9, "For explanations the same weights\nare exported as two ONNX files:\n\n• xai_encoder = \"reader\"\n   text → 128 numbers (slow)\n"
            "• xai_head = \"judge\"\n   128 + 19 inputs → logit (tiny)\n\nmax |Δ logit| vs model.onnx = 0\n(1,000 test complaints)",
            va="top", fontsize=7.8, bbox=dict(boxstyle="round,pad=0.5", fc="#fafaf7", ec="#bbbbbb"))
    ax.plot([0.05, 3.15, 3.15, 0.05, 0.05], [2.0, 2.0, 4.35, 4.35, 2.0], ls=":", color="#7a1f2b", lw=1)
    ax.text(0.1, 0.45, "dotted = the \"reader\" stage (xai_encoder.onnx); everything else = the \"judge\" (xai_head.onnx)",
            fontsize=7.3, color="#7a1f2b")
    fig.tight_layout(); fig.savefig(FIG / "fusion.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def fig_ablation():
    names = ["TF-IDF LR · features", "small network · features", "TF-IDF LR · text", "DistilBERT · text",
             "TF-IDF LR · fusion", "DistilBERT · fusion v4", "DistilBERT · fusion v3 (shipped)"]
    vals = [0.7500, 0.7537, 0.7956, 0.8036, 0.8115, 0.8195, 0.8224]
    lo = [None, 0.744, None, 0.796, None, 0.811, 0.815]; hi = [None, 0.763, None, 0.812, None, 0.827, 0.830]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    cols = ["#bbbbbb"] * 6 + ["#7a1f2b"]
    ax.barh(names, vals, color=cols)
    for i, (v, l, h) in enumerate(zip(vals, lo, hi)):
        if l: ax.plot([l, h], [i, i], color="#1b1b1b", lw=1.2)
        ax.text(0.7015, i, f"{v:.4f}", va="center", fontsize=8, color="white" if i == 6 else "#1b1b1b")
    ax.set_xlim(0.70, 0.84); ax.set_xlabel("within-company ROC-AUC, 2024 test (150,000 complaints); lines = 95 % bootstrap range")
    ax.spines[["top", "right"]].set_visible(False); ax.tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(FIG / "ablation.png", dpi=200); plt.close(fig)


def fig_frames():
    fig, ax = plt.subplots(figsize=(8, 2.8))
    groups = ["text only", "features only", "fusion"]
    within = [0.8916, 0.9276, 0.9457]; company = [0.7956, 0.7500, 0.8115]
    x = range(3)
    ax.bar([i - 0.2 for i in x], within, 0.4, color="#bbbbbb", label="within product × issue")
    ax.bar([i + 0.2 for i in x], company, 0.4, color="#7a1f2b", label="within company")
    for i in x:
        ax.text(i - 0.2, within[i] + 0.003, f"{within[i]:.4f}", ha="center", fontsize=7.5)
        ax.text(i + 0.2, company[i] + 0.003, f"{company[i]:.4f}", ha="center", fontsize=7.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(groups); ax.set_ylim(0.7, 0.97); ax.legend(fontsize=8, frameon=False)
    ax.set_ylabel("ROC-AUC (TF-IDF + LR)", fontsize=8); ax.spines[["top", "right"]].set_visible(False); ax.tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(FIG / "frames.png", dpi=200); plt.close(fig)


def fig_split():
    fig, ax = plt.subplots(figsize=(9, 1.9)); ax.set_xlim(0, 36); ax.set_ylim(0, 2); ax.axis("off")
    for x0, x1, c, t in [(0, 21, "#f3f1ec", "TRAIN  Jan 2022 – Sep 2023\n62,940 rows · all 15,735 payouts + 3 non-payouts each (25 %)"),
                         (21, 25, "#e8eef5", "VAL\nOct–Dec 2023\n80,000\n3.50 %"),
                         (25, 36, "#f6e9ea", "TEST  all of 2024\n150,000 rows · 3,471 payouts (2.31 %)")]:
        box(ax, x0 + 0.1, 0.5, x1 - x0 - 0.2, 1.2, t, c, fs=7.6)
    ax.annotate("", xy=(36, 0.25), xytext=(0, 0.25), arrowprops=dict(arrowstyle="-|>", color="#555555"))
    ax.text(18, 0.02, "time →  (temporal split: learn on the past, test on the future)", ha="center", fontsize=7.5, color="#555555")
    fig.tight_layout(); fig.savefig(FIG / "split.png", dpi=200); plt.close(fig)


for f in (fig_system, fig_distilbert, fig_fusion, fig_ablation, fig_frames, fig_split):
    f()

# ================================================================ CONTENT
# ---------------- title page
story += [Spacer(1, 3.2 * cm),
          Paragraph("PROJECT REPORT", ParagraphStyle("k", fontName="Sans-B", fontSize=11, textColor=MUTED, alignment=TA_CENTER, spaceAfter=18)),
          Paragraph("TriageIQ", ParagraphStyle("t", fontName="Serif-B", fontSize=40, leading=46, alignment=TA_CENTER, textColor=ACCENT, spaceAfter=10)),
          Paragraph("Predicting which consumer-finance complaints will cost the company money — "
                    "a fusion of a fine-tuned DistilBERT language model and point-in-time SQL features, "
                    "deployed as a live web service",
                    ParagraphStyle("s", fontName="Serif-I", fontSize=13.5, leading=19, alignment=TA_CENTER, textColor=INK, spaceAfter=40)),
          Paragraph("Submitted by", ParagraphStyle("a0", fontName="Sans", fontSize=9.5, alignment=TA_CENTER, textColor=MUTED)),
          Paragraph("Shivam Bajaj", ParagraphStyle("a", fontName="Serif-B", fontSize=15, leading=22, alignment=TA_CENTER, spaceAfter=40)),
          Paragraph("Domain: Natural Language Processing · Machine Learning · Data Engineering · MLOps",
                    ParagraphStyle("d", fontName="Sans", fontSize=9.5, alignment=TA_CENTER, textColor=MUTED, spaceAfter=6)),
          Paragraph("Live demo: triageiq-mu.vercel.app · Essay: bajaj30.github.io/TriageIQ · Code: github.com/Bajaj30/TriageIQ",
                    ParagraphStyle("d2", fontName="Sans", fontSize=9, alignment=TA_CENTER, textColor=MUTED, spaceAfter=60)),
          Paragraph("October 2026", ParagraphStyle("dt", fontName="Serif", fontSize=11, alignment=TA_CENTER))]

# ---------------- abstract
h1("Abstract")
p("When a consumer files a complaint with the US Consumer Financial Protection Bureau (CFPB), the company must respond "
  "within 15 days. A small fraction of complaints end <b>“Closed with monetary relief”</b> — the company pays money back. "
  "TriageIQ predicts, at the moment a complaint arrives, the probability that it will end with a payout, so a "
  "compliance desk can route the riskiest complaints to senior analysts and the rest to template replies.")
p("The system is built on 4,826,564 real CFPB complaints (2022–2024) loaded into a PostgreSQL snowflake schema. "
  "Nineteen point-in-time “track-record” features (smoothed company × issue payout rates, volume shares, trends) are "
  "computed in SQL with leak-proof window frames. The complaint narrative is read by a fine-tuned "
  "<b>DistilBERT</b> encoder; an intermediate-fusion network combines its [CLS] representation with entity "
  "embeddings of the SQL features. The model was trained on a free Kaggle T4 GPU, Platt-calibrated, exported to "
  "ONNX, and is served by FastAPI on a 2-core AWS EC2 instance behind NGINX, with a static website on Vercel. "
  "Score explanations are produced with exact and sampled Shapley values and were tested for faithfulness.")
p("On a held-out test set of 150,000 complaints from 2024 (2.31% payouts), the shipped model reaches a "
  "<b>within-company ROC-AUC of 0.8224</b> (95% bootstrap range 0.815–0.830), within product × issue 0.9492, "
  "pooled 0.9731 and PR-AUC 0.4395; reading only the riskiest 10% of complaints catches <b>92.6% of all payouts</b>. "
  "An ablation shows neither modality subsumes the other: text alone 0.8036, SQL features alone 0.7537, fusion 0.8224. "
  "An error analysis suggests the remaining ceiling is set by company decisions that are not visible in the text.")
p("<b>Keywords:</b> text classification, DistilBERT, transformer fine-tuning, multimodal fusion, point-in-time "
  "feature engineering, target encoding, class imbalance, calibration, Shapley values, ONNX, FastAPI.")

# ---------------- TOC
story.append(PageBreak())
story.append(Paragraph("Table of Contents", H1))
toc = TableOfContents()
toc.levelStyles = [ParagraphStyle("toc1", fontName="Sans-B", fontSize=10, leading=15, leftIndent=0),
                   ParagraphStyle("toc2", fontName="Serif", fontSize=9.3, leading=12.5, leftIndent=16)]
story.append(toc)

# ---------------- 1 Introduction
h1("1. Introduction")
h2("1.1 Background")
p("The CFPB runs a public complaint database: anyone with a problem with a bank, lender, debt collector or credit "
  "bureau can file a complaint, which is forwarded to the company and published. Each complaint is eventually closed "
  "in one of a few ways; the one that matters most to the company is <i>closed with monetary relief</i> — a refund, "
  "a reversed fee or compensation. Payouts are rare: 1.26% of all complaints in 2022–2024, and 2.16% of those that "
  "carry a written narrative.")
h2("1.2 Motivation")
p("A complaints team has a fixed amount of senior-analyst time and a regulatory deadline. Reading every complaint "
  "carefully is expensive; routing by product type alone lets expensive cases inside “low-risk” products slip through. "
  "The decision that matters is a ranking problem: <i>which complaints should a senior person read first?</i>")
code("complaint arrives  →  P(monetary relief)  →  high: senior analyst  /  low: template response")
h2("1.3 Objectives")
bullets([
    "Build a reproducible data pipeline over the full public dataset (no synthetic data), with every feature computable "
    "only from what existed on the day the complaint arrived.",
    "Measure how much the complaint <b>text</b> and the company's <b>track record</b> each contribute, and whether "
    "combining them helps (the ablation).",
    "Fine-tune a transformer (DistilBERT) and fuse it with the SQL features; beat a TF-IDF + logistic-regression baseline.",
    "Calibrate the output into an honest probability and derive a routing threshold from capacity.",
    "Deploy the model as a public, low-cost web service, and explain each score faithfully.",
])
h2("1.4 Scope and constraints")
bullets([
    "Free tier only: training on Kaggle's free T4 GPU; serving on a small CPU server paid by $140 AWS credits (≈ $21/month).",
    "Label = company cost (monetary relief), not consumer harm — the CFPB publishes no severity label.",
    "One source of truth for features: all feature logic lives in SQL; Python never re-implements a feature.",
    "Reproducibility: SEED = 42, versioned training sets with sha256 manifests, code for every quoted number.",
])

# ---------------- 2 Literature
h1("2. Literature Review and Background")
h2("2.1 Text classification: from bag-of-words to transformers")
p("<b>Bag-of-words and TF-IDF.</b> Classic text classifiers represent a document as word counts, ignoring order. "
  "TF-IDF (term frequency × inverse document frequency) up-weights words frequent in a document but rare across the "
  "corpus. Paired with logistic regression, it remains a strong, interpretable baseline for document classification.")
p("<b>Transformers.</b> The transformer (Vaswani et al., 2017) replaces recurrence with <i>self-attention</i>: every "
  "token attends to every other token, so a word's representation depends on its context (“charge my card” vs “in "
  "charge of”). BERT (Devlin et al., 2019) stacks transformer encoder layers and is pre-trained with <i>masked "
  "language modelling</i> (guess hidden words) on large unlabelled corpora, then fine-tuned on a downstream task — "
  "<i>transfer learning</i>.")
p("<b>Knowledge distillation and DistilBERT.</b> Distillation (Hinton et al., 2015) trains a small <i>student</i> to "
  "mimic a large <i>teacher</i>'s soft output distribution. DistilBERT (Sanh et al., 2019) halves BERT's depth to 6 "
  "layers; its authors report it is 40% smaller and 60% faster while keeping about 97% of BERT's language "
  "understanding. It was chosen here because it fits a free T4 for training and a 2-core CPU for serving.")
p("<b>Alternatives considered.</b> DeBERTa-v3 (He et al., 2021) is stronger at 512 tokens; long-context encoders "
  "(ModernBERT, jina-embeddings-v2 with 8k context) and chunk-and-pool strategies handle long documents. Section 7.6 "
  "explains why none was needed.")
h2("2.2 Multimodal / tabular + text fusion")
p("When a prediction depends on both free text and structured data, three designs are common: <i>early fusion</i> "
  "(concatenate raw features into one model, as done with TF-IDF), <i>late fusion</i> (average the outputs of separate "
  "models), and <i>intermediate fusion</i> (learn a representation of each modality, concatenate them, and train a "
  "joint head). TriageIQ uses intermediate fusion with <i>entity embeddings</i> for categorical inputs (Guo & Berkhahn, 2016).")
h2("2.3 Feature engineering for event data")
p("<b>Target encoding</b> replaces a high-cardinality category (a company) by its average outcome; it is powerful but "
  "leaks easily. <b>Empirical-Bayes smoothing</b> shrinks small-sample rates toward a prior: (payouts + K·prior) ÷ "
  "(complaints + K). <b>Point-in-time correctness</b> — computing each feature only from data available at the event "
  "time — is the standard defence against future leakage in feature stores.")
h2("2.4 Class imbalance, calibration and evaluation")
p("With ~2% positives, accuracy is meaningless (the <i>accuracy paradox</i>). Undersampling (case-control sampling) "
  "with a <i>prior correction</i> on the logit (King & Zeng, 2001), weighted losses, focal loss (Lin et al., 2017) and "
  "SMOTE (Chawla et al., 2002) are standard remedies. Neural networks are often mis-calibrated (Guo et al., 2017); "
  "<i>Platt scaling</i> (Platt, 1999), temperature scaling and <i>isotonic regression</i> map scores to honest "
  "probabilities. ROC-AUC, PR-AUC (better for rare classes) and recall-at-k are the usual ranking metrics.")
h2("2.5 Explainability")
p("<b>Shapley values</b> (Shapley, 1953), popularised for ML as SHAP (Lundberg & Lee, 2017), share a prediction "
  "fairly among input “players”; their contributions add up exactly to the prediction. <b>LIME</b> (Ribeiro et al., "
  "2016) fits a local weighted linear model on perturbed inputs. Faithfulness tests (deleting the top-attributed "
  "inputs) check that an explanation reflects the model rather than decoration.")

# ---------------- 3 Problem
h1("3. Problem Statement and System Requirements")
h2("3.1 Problem statement")
p("<i>Given a newly arrived CFPB complaint — company, product, sub-product, issue, state, tags and the consumer's "
  "written narrative — estimate the probability that it will be closed with monetary relief, using only information "
  "available on the day it arrived, and rank complaints so that senior analysts read the riskiest first.</i>")
h2("3.2 Formulation")
bullets([
    "Task: binary classification, used as ranking. y = 1 if the company response is “Closed with monetary relief”, else 0 "
    "(untimely / never-answered and the 19 unknown outcomes are labelled 0).",
    "Input: identifiers + text, never pre-computed features (the API looks features up in SQL).",
    "Output: calibrated probability p and a route (senior if p ≥ 0.0367, the riskiest 10% of 2024).",
])
h2("3.3 Functional requirements")
bullets(["POST /predict: score a typed-in complaint (names + text).",
         "GET /complaint/random and /complaint/{id}: score a real 2024 complaint and show what actually happened.",
         "GET /options/*, /model-info, /health; POST /explain with a ticket-based job queue.",
         "A public website and API documentation (Swagger UI at /docs)."])
h2("3.4 Non-functional requirements")
bullets(["No leakage; temporal evaluation; reproducibility.",
         "Train/serve parity: same SQL formulas and the same text-cleaning function in training and serving.",
         "Latency suitable for triage (sub-second typical), runs on a 2-core ARM CPU with ~2 GB RAM.",
         "Security: database not reachable from outside; origin locked to the website by a secret header; rate limits.",
         "Cost: free credits only."])

# ---------------- 4 Dataset & EDA
h1("4. Dataset and Exploratory Text Analysis")
h2("4.1 Source and populations")
p("The CFPB Consumer Complaint Database (public, real). The raw CSV is 9.2 GB with 17.4 million complaints "
  "(Dec 2011 – Aug 2026). The project uses the window 2022-01-01 to 2024-12-31. Three populations are kept distinct "
  "and every number states which one it comes from:")
table([["population", "what it is", "rows", "payouts", "base rate"],
       ["all complaints (F1)", "every complaint in the window; feature population", "4,826,564", "60,952", "1.26%"],
       ["complaints with text (F2)", "complaints with a published narrative; modelling population", "1,639,068", "35,375", "2.16%"],
       ["training set v3", "sampled and split train / val / test", "292,940", "—", "see Section 8.1"]],
      [3.4, 6.6, 2.2, 1.8, 1.8], "Populations (Context/FACTS.md).")
p("<b>Why keep complaints with no text?</b> The 3,187,496 complaints without a narrative hold 25,577 payouts — 42% of "
  "all positives. Company payout rates computed without them would be biased by a different amount for every company. "
  "Payouts also fall year on year (complaints with text: 2022 2.74% · 2023 2.51% · 2024 1.71%), so the 2024 test is "
  "genuinely harder than training.")
h2("4.2 Corpus profiling at scale")
p("A 9.2 GB CSV cannot be loaded at once. It was streamed in 250,000-row chunks, only needed columns kept, and cached "
  "as Parquet (columnar, compressed) — <font face='Mono' size='8.5'>Data/EDA.ipynb</font>.")
h2("4.3 Real or machine-written? A five-test authenticity gate")
p("Synthetic (LLM-made) text would make a language model pointless, so authenticity was tested numerically:")
table([["test", "what it measures", "result", "suspicious if"],
       ["exact-duplicate rate", "share of texts identical to another (MD5 of normalised text)", "19.8% raw → 0.3% after the copy cap (early sample)", "—"],
       ["sentence-length coefficient of variation", "std ÷ mean of sentence lengths; people write unevenly, LLMs regularly", "0.94", "< 0.35"],
       ["type-token ratio (TTR)", "distinct words ÷ total words (vocabulary variety)", "0.065 raw, 0.081 after removing copy-paste floods", "< 0.08"],
       ["top repeated opener", "share of texts starting with the same 5 words", "3.7% — Fair Credit Reporting Act wording copied from forums (evidence of humans)", "> 5%"],
       ["unfilled placeholders", "{name}-style template slots", "0 real ones", "> 0"]],
      [3.4, 4.8, 4.5, 2.3], "Authenticity tests on the narratives.")
bullets([
    "<b>Heaps' law:</b> longer texts reuse more words, so TTR only compares fairly at equal length — always measured on exactly 100,000 words.",
    "<b>Lesson 1:</b> the “placeholders” flagged at first were CFPB's {XXXX} amount redactions — the regex <font face='Mono' size='8.5'>\\{[a-z_]+\\}</font> ran "
    "case-insensitive and matched capital X. Print the matches; don't trust a counter.",
    "<b>Lesson 2:</b> 40-character “words” were URLs, not corrupted text.",
])
h2("4.4 Duplicate anatomy and near-template text")
bullets(["41% of raw narratives sit in a duplicate group; the largest group has 30,110 copies of one template.",
         "Unique texts pay out 3.84%; texts seen 2+ times pay 0.05% or less (complaints with text, from April 2022).",
         "<b>Text hashing:</b> text_hash = md5 of lower-cased, trimmed, whitespace-collapsed text finds exact copies cheaply "
         "(sql/01_schema/07_narrative_columns.sql)."])
h2("4.5 Redaction analysis")
bullets(["The CFPB hides private details as XXXX and dates as XX/XX/XXXX.",
         "70.3% of complaints with text contain XXXX; 15.5% of all word-pieces are blanks (20,000-complaint sample).",
         "20.2% of complaints are ≥ 20% blanks, 8.6% are ≥ 40%."])
h2("4.6 Length analysis")
bullets(["1.24 word-pieces per word (median; p90 1.51), so 512 pieces ≈ 410 words.",
         "91.8% of complaints fit in 512 pieces (72.7% at 256, 98.1% at 1,024; 20k sample). Tokens p50 149, p99 1,341.",
         "In the 2024 test set 8.4% of complaints (12,602) are cut at 512; they pay 3.41% vs 2.21%.",
         "Payout rate peaks for texts of 512–1k tokens, so long complaints matter."])
h2("4.7 Dollar amounts")
p("Amounts appear as {$35.00}. 19.2% of complaints with text mention an amount; they pay 7.10% vs 0.99% and hold 63% of "
  "payouts (22,306 / 35,375). Small amounts pay most (under $100: 11.70%; $10k+: 4.09%).")

# ---------------- 5 Data engineering
h1("5. Data Engineering and Feature Pipeline")
h2("5.1 Database schema (snowflake)")
p("PostgreSQL 16 with pgvector in Docker (16 GB). A central fact table <font face='Mono' size='8.5'>fact_complaint</font> "
  "(4,826,564 rows) references dimension tables for company (4,946), product (11), sub-product (62), issue (93), "
  "sub-issue (293) and state (62). The narrative lives in its own extension table (1,639,068 rows), and outcomes live "
  "in an event log <font face='Mono' size='8.5'>complaint_events</font> (14,479,692 rows) — never on the fact table, so "
  "using the label requires a deliberate join (target-leakage guard). Key decisions:")
bullets(["Surrogate integer keys; child dimensions unique on (parent_id, child_name) — names repeat across parents "
         "(87.5% of rows have a sub-product that appears under more than one product).",
         "Composite foreign keys make the database reject a sub-product under the wrong product.",
         "Issue and product are independent dimensions (55% of issues span several products).",
         "NULL child → a ‘(not specified)’ member, never a NULL foreign key (inner joins drop NULLs silently).",
         "<b>Taxonomy crosswalks:</b> in Aug 2023 the CFPB renamed/split products — 14 raw names map to 11 canonical "
         "products (1,334,958 complaints re-routed by sub-product); one renamed issue re-routed 337,252 complaints "
         "(893,566 complaints share the canonical issue), so company histories do not reset mid-window.",
         "Load validated against expectations computed independently in pandas (21/21 checks)."])
h2("5.2 Label")
p("<font face='Mono' size='8.5'>v_label</font>: 4,826,564 rows, 60,952 paid (1.26%). The 2,785 untimely (never "
  "answered) complaints and 19 NULL outcomes are labelled 0 — no money left the company.")
h2("5.3 Point-in-time features (the “track record”)")
p("Seven SQL steps build <font face='Mono' size='8.5'>mv_features</font> (one row per complaint, ~80 s) and the view "
  "<font face='Mono' size='8.5'>v_model_input</font> (19 model inputs). Three window-frame patterns, verified on PostgreSQL:")
code("outcome rates : ORDER BY date_received RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING\n"
     "volume counts : ORDER BY date_received RANGE BETWEEN '90 days' PRECEDING AND '1 day' PRECEDING\n"
     "sequence      : ORDER BY date_received, complaint_id")
p("The default frame would include the current row's own label, and 43.46% of company-days hold more than one "
  "complaint (max 4,245 in a day), so “before this complaint” needs these explicit frames. Outcomes count only after a "
  "60-day lag — the time a company takes to answer.")
bullets([
    "<b>Target encoding, fitted on all 4.8M complaints:</b> fitted on the resampled training set it cost 0.032 AUC "
    "(25% positives vs ~3%), so entity rates are computed in Postgres over every complaint.",
    "<b>Empirical-Bayes smoothing</b> (payouts + K × prior) ÷ (complaints + K), prior = the <i>product</i> rate (a global "
    "average is a credit-reporting average: 83.2% of rows, 3.3% of payouts). <b>K = 5 was measured:</b> company × issue "
    "with < 200 history, AUC 0.8690 at K = 0 vs 0.8901 at K = 5 (0.8754 at K = 50, 0.8495 at K = 500); Brier best at K = 5.",
    "<b>Cold-start flags:</b> “no history” ≠ “never pays”; an explicit 0/1 flag says which it is.",
    "<b>Multi-hot flags:</b> “Older American” and “Servicemember” can both be ticked → two independent flags (10.08% and "
    "2.43% payout vs 1.06% untagged).",
    "<b>Ratios and log-ratios instead of raw counts:</b> shares of national volume over 90 days; trend = "
    "ln((last 90 days + 1) ÷ (the 90 before + 1)).",
    "<b>Covariate shift (“clock” features):</b> counts that grow with the calendar teach <i>when</i>, not <i>what</i>; removed. "
    "Check: 19 inputs 0.7500 vs 19 + the removed ones 0.7499.",
    "<b>Feature selection by meaning, then by test:</b> 48 stored columns, 19 model inputs (Appendix A).",
])

# ---------------- 6 Text preprocessing
h1("6. Text Preprocessing and Tokenisation")
h2("6.1 Cleaning")
bullets([
    "<b>Normalisation:</b> lower-case, trim and collapse whitespace before hashing, so trivial differences don't hide copies.",
    "<b>Typed placeholder tokens instead of deletion:</b> each run of blanks becomes one marker, [DATE] or [REDACTED]. "
    "This keeps the information that something was hidden there (where and how many blanks appear is itself signal), "
    "while freeing room in the 512-piece window. Median length 238 → 109 tokens on heavy-blank texts; over-512 12.1% → 3.6%.",
    "<b>One function, two callers:</b> SQL <font face='Mono' size='8.5'>clean_narrative()</font> is used by both the "
    "training export and the live API — no train/serve skew.",
    "<b>Regex information extraction:</b> a SQL function reads the largest {$…} amount (Section 4.7).",
    "<b>Real-word count quality filter:</b> n_real_words = alphabetic words minus XX… blanks; training keeps complaints with "
    "≥ 20 real words, and the API enforces the same rule (HTTP 422 otherwise).",
    "<b>Copy cap and group-aware splitting:</b> at most 25 copies of any text; a text belongs to the split where it first "
    "appeared, so identical complaints can't be in both training and test (group leakage). The v2 set had 721 narratives "
    "straddling splits; v3 fixes it.",
])
h2("6.2 Considered and rejected — measured first")
bullets(["<b>Lemmatisation</b> (“charged” → “charge”): even a perfect one fits only 22% of the long complaints into 512, and "
         "it hands a transformer unnatural text.",
         "<b>Stopword removal:</b> fits 55%, but deletes <i>not, no, never</i> — “I did <b>not</b> authorise this” becomes “authorise”.",
         "Both are tools for word-counting models, not for transformers."])
h2("6.3 Subword tokenisation (WordPiece)")
bullets([
    "Text is split into pieces from a fixed vocabulary of 30,522: “chargeback” → charge ##back, “overdraft” → over ##dra ##ft.",
    "A CFPB blank XXXX costs 2 pieces (xx ##xx) and a hidden date 6 — hence the markers.",
    "DistilBERT-<i>uncased</i> also lower-cases and strips accents first.",
    "<b>Special tokens:</b> [CLS] (start; its output summarises the text), [SEP] (end), [PAD] (filler). [DATE] and "
    "[REDACTED] were registered as <i>additional special tokens</i> and the embedding table resized 30,522 → 30,524 — as "
    "plain text, [REDACTED] would cost 5 pieces.",
    "<b>Maximum length and truncation:</b> at most 512 pieces; the first 510 are kept plus [CLS]/[SEP] (“head” truncation). "
    "Head + tail truncation (keep the start and the end) was built but not needed (Section 7.6).",
    "<b>Attention mask:</b> 1 for real pieces, 0 for padding, so the model ignores filler.",
    "<b>Dynamic padding vs length-grouped batching:</b> padding each batch to its longest text gave no speed-up (1.00×) "
    "because almost every random batch holds one long complaint; grouping similar lengths (mega-batches of 50 batches, "
    "sorted, then shuffled) cut padded pieces <b>2.23×</b>.",
    "<b>Tokeniser parity:</b> the serving tokeniser (Rust <i>tokenizers</i>) gave the same pieces as training's "
    "(<i>transformers</i>) on 1,000 of 1,000 test complaints.",
])

# ---------------- 7 Architectures
h1("7. Model Architectures")
p("Five model families were trained and compared on the same 2024 test set. All neural variants come from one notebook "
  "(<font face='Mono' size='8.5'>training/fusion_distilbert.ipynb</font>) whose switch MODE = fusion / text / features "
  "decides which branches exist.")
h2("7.1 Baseline: TF-IDF + logistic regression")
bullets([
    "<b>TF-IDF</b> with unigrams and bigrams (ngram_range = (1, 2), so “not authorised” is one feature), at most 80,000 "
    "features, min document frequency 5, <b>sublinear TF</b> (1 + log count), accents stripped.",
    "<b>Track-record inputs:</b> one-hot encoding for categories; numbers standardised to mean 0, std 1 (fit on train only).",
    "<b>Early fusion:</b> TF-IDF columns and track-record columns glued side by side into one sparse matrix.",
    "<b>Logistic regression</b> (liblinear): a weighted sum squeezed into a probability by the sigmoid — linear, interpretable, fast.",
    "Three variants: text only, features only, fusion. Fusion within-company 0.8115 — the bar to beat.",
])
h2("7.2 DistilBERT encoder")
figure(FIG / "distilbert.png", 16.5, "DistilBERT-base-uncased as used in TriageIQ.")
p("<b>Embeddings.</b> Each word-piece id is looked up in a 30,524 × 768 table (the two added markers included) and added "
  "to a learned position embedding (512 × 768), followed by LayerNorm and dropout 0.1. Unlike BERT, DistilBERT has no "
  "segment (token-type) embeddings.")
p("<b>Self-attention.</b> In each layer every piece forms a query, key and value (768 → 768 each); 12 heads of 64 "
  "dimensions compute softmax(QK<super>T</super>/√64)·V in parallel, so each head can attend to a different relation. "
  "The attention mask sets padding scores to −∞. Outputs are concatenated, projected back to 768, and added to the input "
  "(residual) with LayerNorm.")
p("<b>Feed-forward network.</b> Each position then passes through Linear 768 → 3,072, GELU, Linear 3,072 → 768, dropout, "
  "residual and LayerNorm. Six such blocks are stacked.")
p("<b>Pre-training by distillation.</b> The student was initialised from every second layer of BERT-base and trained on "
  "BookCorpus + English Wikipedia with a triple loss: soft-target distillation loss against the teacher (temperature "
  "softmax), the masked-language-modelling loss, and a cosine loss aligning hidden states. BERT's next-sentence task and "
  "pooler were dropped.")
table([["component", "shape / setting", "parameters"],
       ["word-piece embeddings", "30,524 × 768", "23,442,432"],
       ["position embeddings + LayerNorm", "512 × 768, 2 × 768", "394,752"],
       ["per transformer block: attention (Q, K, V, O)", "4 × (768 × 768 + 768)", "2,362,368"],
       ["per block: feed-forward", "768→3,072→768", "4,722,432"],
       ["per block: 2 LayerNorms", "2 × 2 × 768", "3,072"],
       ["6 blocks", "6 × 7,087,872", "42,527,232"],
       ["<b>encoder total</b>", "", "<b>≈ 66.36 M</b>"]],
      [6.2, 5.0, 3.4], "DistilBERT encoder parameter count (after resizing for [DATE] and [REDACTED]).", bold_last=True)
p("<b>[CLS] pooling.</b> The 768-number vector at position 0 ([CLS]) represents the whole complaint and feeds the "
  "task layers. <b>Transfer learning / fine-tuning:</b> training starts from the pre-trained weights, so the model reuses "
  "general English knowledge; all encoder weights are updated from epoch 2.")
h2("7.3 Fusion network (shipped model)")
figure(FIG / "fusion.png", 16.5, "The DistilBERT fusion network (multimodal, intermediate fusion) and its calibration.")
p("<b>Text branch:</b> [CLS] 768 → Linear → 128, GELU, dropout 0.1. <b>Table branch:</b> each categorical id gets a "
  "learned <b>entity embedding</b> — product 4 numbers, sub-product 8, issue 12, state 8 (similar categories end up close "
  "together) — concatenated with the 15 numeric inputs (47 numbers) → Linear 47 → 128, GELU, dropout → Linear 128 → 64, "
  "GELU. <b>Feature scaling:</b> log1p for the heavy-tailed “days since last complaint”, then standardisation with "
  "training-only mean and std, saved in <font face='Mono' size='8.5'>preprocessing.json</font> and reused unchanged when "
  "serving. <b>Head:</b> concatenate 128 + 64 = 192 → Linear 64, GELU, dropout → Linear 1 = the logit. "
  "GELU is a smooth ReLU; dropout randomly silences units during training so the model can't lean on any one.")
table([["part", "layers", "parameters (approx.)"],
       ["DistilBERT encoder", "6 transformer blocks", "66.36 M"],
       ["text branch", "Linear 768→128", "98,432"],
       ["entity embeddings", "4 tables (dims 4 / 8 / 12 / 8)", "≈ 2,200"],
       ["table branch", "Linear 47→128, Linear 128→64", "14,400"],
       ["fusion head", "Linear 192→64, Linear 64→1", "12,417"],
       ["<b>total</b>", "", "<b>≈ 66.5 M</b> (ONNX file 266 MB fp32)"]],
      [4.0, 6.0, 4.6], "Fusion model size.", bold_last=True)
h2("7.4 Ablation variants of the same network")
bullets(["<b>Text only (MODE = text):</b> encoder → text branch (128) → head Linear 128→64 → 1. Within-company 0.8036.",
         "<b>Features only — “small network” (MODE = features):</b> no language model; entity embeddings + numerics → table "
         "branch (64) → head 64→64→1. Within-company 0.7537 (v3) and 0.7779 (v4 with amount features).",
         "<b>Fusion v4:</b> the same fusion network with 23 inputs (+ has_amount, log_max_amount and two recent 365-day rates). "
         "0.8195 vs 0.8224 — equal within noise, so the simpler v3 (19 inputs) ships."])
h2("7.5 Two-stage export for explanations")
p("For explanations the trained weights are split into a <b>reader</b> (DistilBERT + text branch → 128 numbers, "
  "<font face='Mono' size='8.5'>xai_encoder.onnx</font>, 266 MB) and a <b>judge</b> (table branch + head → logit, "
  "<font face='Mono' size='8.5'>xai_head.onnx</font>, 0.1 MB). Reader + judge reproduce model.onnx exactly (max |Δ logit| "
  "= 0 on 1,000 test complaints). In production the scorer runs the two halves, so one DistilBERT copy is shared by "
  "scoring and explaining (api ~630 MiB RAM).")
h2("7.6 Encoders and strategies considered, not used")
bullets(["<b>DeBERTa-v3-base</b> (gradient accumulation was built for it: half batch × 2 steps): skipped — the error analysis "
         "says the missing information isn't in the text.",
         "<b>Long-context models</b> (ModernBERT, jina 8k) and <b>chunk-and-pool</b>: not needed. On complaints cut at 512, "
         "DistilBERT fusion scored 0.9614 — equal to the read-every-word TF-IDF fusion (0.9614); fits 0.9741 vs 0.9722.",
         "<b>int8 quantisation</b> (8-bit weights): not needed — the server has RAM to spare (api ~550 MiB of ~1.8 GB) and "
         "0.2 s is fast enough for triage."])

# ---------------- 8 Training
h1("8. Training Methodology")
h2("8.1 Temporal split and sampling")
figure(FIG / "split.png", 16, "Training set v3: temporal split (train Jan 2022 – Sep 2023, validate Oct–Dec 2023, test 2024).")
bullets([
    "<b>Temporal split:</b> test on the future, never a random sample.",
    "<b>Data leakage, and how each kind was blocked:</b> <i>target leakage</i> — the outcome lives in a separate event table and "
    "post-intake columns (date sent, company response, timely?, public response) are never features; <i>future leakage</i> — "
    "point-in-time features; <i>group leakage</i> — the duplicate-text rule; <i>preprocessing leakage</i> — scalers fitted on train only.",
    "<b>Class imbalance — options:</b> undersampling (used: every payout + 3 non-payouts each → 62,940 rows, 25% payouts); "
    "weighted loss on all rows (~34× weight on payouts); SMOTE (rejected for text — two complaints can't be blended into a "
    "real one; fine for numeric data); focal loss (a variant of weighting).",
    "<b>Case-control sampling + prior correction:</b> keeping 8.92% of non-payouts inflates the odds of a payout; adding "
    "ln(0.0892) = <b>−2.4165</b> to every logit undoes it exactly (read from the manifest, never typed).",
    "<b>Learning-curve test (“halve it before you double it”):</b> training on half the data gave 0.8166 vs 0.8224 — inside "
    "the noise, so more data was unlikely to help; this saved ~3.5 GPU-hours.",
])
table([["setting", "value", "why"],
       ["loss", "binary cross-entropy on the logit (BCEWithLogitsLoss)", "punishes confident wrong answers hardest; numerically stable"],
       ["optimiser", "AdamW, weight decay 0.01", "decoupled decay shrinks weights a little each step against over-fitting"],
       ["discriminative learning rates", "2e-5 encoder · 1e-3 new layers", "gentle on pre-trained weights, fast for random ones"],
       ["schedule", "linear warm-up over 5% of steps, then linear decay", "avoids large early updates"],
       ["gradual unfreezing (ULMFiT)", "epoch 1: encoder frozen; epochs 2–3: everything", "random head gradients can't damage pre-trained knowledge"],
       ["gradient clipping", "global norm 1.0", "one bad batch can't take a huge step"],
       ["mixed precision", "fp16 autocast + GradScaler (T4 has no bf16)", "half the memory, faster maths; scaler stops tiny gradients rounding to 0"],
       ["gradient accumulation", "built for DeBERTa (½ batch × 2)", "not used in the final run"],
       ["batch size", "16 train · 64 eval; length-grouped batches", "2.23× fewer padded pieces"],
       ["early stopping", "on validation PR-AUC, ≤ 3 epochs, patience 1", "PR-AUC focuses on the rare class"],
       ["reproducibility", "seed 42; dataset sha256 checked vs manifest", "same data, same run"],
       ["compute", "≈ 481 s per epoch on one free Kaggle T4", "3 epochs ≈ 25 min"]],
      [3.6, 5.4, 5.6], "Training configuration of the DistilBERT fusion model.", heading="8.2 Optimisation")

# ---------------- 9 Evaluation
h1("9. Evaluation and Results")
h2("9.1 Three evaluation frames")
p("A model earns easy points by knowing that credit-card complaints pay more often than credit-report disputes — true, but "
  "useless to a bank sorting its own queue. So AUC is reported in three frames: <b>pooled</b> (any two complaints), "
  "<b>within product × issue</b> (holding the case type fixed) and <b>within company</b> (the deployment view — the headline). "
  "Within-group AUCs are averaged weighted by group size over groups with enough positives.")
figure(FIG / "frames.png", 13, "The flip: holding product and issue fixed, the track record wins; inside one company's queue, the text wins (TF-IDF + LR, 2024 test).")
h2("9.2 Every metric")
table([["metric", "what it answers", "value (2024 test, DistilBERT fusion)"],
       ["ROC-AUC, within company (headline)", "inside one company's queue, how often a payout is ranked above a non-payout", "<b>0.8224</b>"],
       ["ROC-AUC, within product × issue", "the same, holding product and issue fixed", "0.9492"],
       ["ROC-AUC, pooled", "any two complaints; inflated by between-group differences", "0.9731"],
       ["PR-AUC (average precision)", "how clean the top of the list is; also picks the best epoch", "0.4395"],
       ["recall at top-k", "share of payouts in the riskiest k%", "top 10% → <b>92.6%</b>"],
       ["bootstrap 95% range", "is a difference real or luck? 1,000 resamples inside each company", "0.815–0.830"],
       ["slice AUC", "do complaints cut at 512 suffer?", "cut 0.9614 vs fits 0.9741"],
       ["single-feature AUC", "signal in one input alone", "used to screen features"],
       ["calibration: mean predicted vs actual", "do “3%” predictions pay about 3%?", "3.11% vs 2.31% before the fix"],
       ["reliability table (10 equal-count buckets)", "calibration bucket by bucket", "riskiest bucket 28.6% → 21.2% predicted vs 19.7% actual"],
       ["Brier score", "mean squared error of probabilities (also chose K)", "0.01474 (Platt fit Jan–Jun, scored Jul–Dec 2024)"],
       ["log loss", "penalty for confident mistakes", "0.04939 (same check)"],
       ["ECE", "average gap, predicted vs actual", "0.00172 (same check)"],
       ["Spearman rank correlation", "did the ONNX export keep the ranking?", "0.999999 vs the GPU model"]],
      [4.3, 6.0, 4.3], "Evaluation metrics (NLP.md §10, FACTS.md).")
p("<b>Deliberately not used:</b> <i>accuracy</i> — “never pays” scores 97.7% on 2024 (the accuracy paradox); <i>F1 / F2</i> — "
  "they need a fixed cut-off; F2 is the candidate if a desk ever sets one from its capacity.")
h2("9.3 Ablation study")
figure(FIG / "ablation.png", 15, "Ablation: every model on the same 150,000-complaint 2024 test set.")
table([["model", "inputs", "within-company", "within P × I", "PR-AUC", "top 10% catches"],
       ["TF-IDF + LR", "text", "0.7956", "0.8916", "0.3523", "87.2%"],
       ["TF-IDF + LR", "SQL features", "0.7500", "0.9276", "0.3645", "88.8%"],
       ["TF-IDF + LR", "text + SQL", "0.8115", "0.9457", "0.4262", "91.7%"],
       ["small network", "SQL features", "0.7537 (0.744–0.763)", "0.9266", "0.3847", "89.1%"],
       ["small network · v4", "SQL features + amounts", "0.7779 (0.769–0.787)", "0.9403", "0.4094", "90.7%"],
       ["DistilBERT", "text", "0.8036 (0.796–0.812)", "0.9163", "0.3759", "88.8%"],
       ["DistilBERT fusion · v4", "text + 23 SQL", "0.8195 (0.811–0.827)", "0.9514", "0.4426", "92.9%"],
       ["<b>DistilBERT fusion · v3 (shipped)</b>", "text + 19 SQL", "<b>0.8224 (0.815–0.830)</b>", "0.9492", "0.4395", "<b>92.6%</b>"]],
      [3.7, 2.7, 3.3, 1.7, 1.5, 1.7], "Model comparison on training set v3 (FACTS.md).", bold_last=True)
p("Neither modality subsumes the other. The riskiest 10% catches 92.6% of payouts with fusion vs 88.8% text-only — "
  "about 130 more payouts in the 2024 test. <b>Information overlap:</b> the dollar-amount feature lifted the features-only "
  "model (0.7537 → 0.7779) but not the fusion (0.8195 vs 0.8224), because DistilBERT already reads “$760” in the text.")
h2("9.4 Error analysis — why within-company stops near 0.82")
bullets(["<b>Misses</b> are mostly “surprise” payouts on complaint types that almost never pay (credit-report disputes, "
         "login problems; company × issue rate ≈ 0.001–0.05) — likely goodwill credits that read like thousands that never pay.",
         "<b>False alarms</b> read exactly like refund cases (named fee, amount, unauthorised charge) — the company just didn't pay.",
         "Either way the deciding fact is a company decision that isn't in the text: the ceiling looks like unobservable "
         "decisions, not a weak reader."])

# ---------------- 10 Calibration
h1("10. Calibration and Decision Rule")
bullets([
    "<b>Prior correction</b> (−2.4165) fixes the case-control sampling only: after it the model still predicted 3.11% on 2024 "
    "vs 2.31% actual, because payouts fall year on year.",
    "<b>Platt scaling</b> p = σ(a·z + b) with z = logit − 2.4165, fitted on the newest labelled data (Jul–Dec 2024, n = 83,130): "
    "a = 0.7025 fixes over-confidence, b = −0.7621 fixes drift. Checked on later months: fit Jan–Jun → Jul–Dec predicted 2.22% "
    "vs actual 2.10% (offset only: 2.91%).",
    "<b>Intercept shift</b> (b only) was compared: fixes the drift but not the over-confidence (Brier 0.01494 vs 0.01474).",
    "<b>Temperature scaling</b> (a only), the usual neural-network variant, was not needed — Platt covers it.",
    "<b>Isotonic regression</b> was rejected: its ties lowered the ranking score (0.8296 → 0.8290).",
    "<b>Monotone transforms never change AUC</b> — the order is kept.",
    "<b>Threshold from capacity, not 0.5:</b> the riskiest 10% go to seniors, p ≥ 3.67%. In 2024, 21.4% of that group paid vs "
    "0.19% in the template group.",
])
h2("10.1 Drift types met")
bullets(["<b>Label / prior shift:</b> payouts 2.74% → 1.71% (complaints with text, 2022 → 2024) — handled by recalibration.",
         "<b>Covariate shift:</b> the clock features — removed.",
         "<b>Concept drift:</b> a company changing its policy — visible in the error analysis. Ranking did not decay in 2024 "
         "(within-company Jul–Dec 0.8296 vs full year 0.8224)."])

# ---------------- 11 XAI
h1("11. Explainability: “Why this score?”")
h2("11.1 Method")
bullets([
    "<b>Shapley values (the maths behind SHAP):</b> add players one at a time in every order, note each one's jump, average. "
    "The shares add up exactly: typical score + all shares = this score. Players = the words + 10 groups of the 19 inputs "
    "(inputs that only make sense together, like product + sub-product, form one player). “Removing” a player = using a "
    "typical complaint's value: 100 background complaints from Oct–Dec 2023. Computed in log-odds; shown as odds multipliers "
    "(×2 = doubles the odds).",
    "<b>Two-stage model:</b> words vs inputs needs only the tiny judge, so all 2<super>11</super> = 2,048 combinations are computed exactly.",
    "<b>Sentence attribution by deletion:</b> pieces of text (sentences, ≤ 16) are players; removing one = deleting it and "
    "re-reading. ≤ 8 pieces: all combinations (exact); more: 16 random orders in reverse pairs (antithetic sampling). "
    "Caveat: text with sentences deleted is text the model never saw.",
    "<b>LIME</b> as a cross-check: delete random subsets, weight each by closeness to the full text, fit a weighted linear model.",
])
h2("11.2 Faithfulness tests")
p("200 complaints from the 2024 test set (100 paid, 100 not; training/results/xai_v3.json):")
bullets(["Deleting the top-ranked piece lowers the logit 0.37 on average vs 0.04 for a random piece — the top piece wins in "
         "<b>91%</b> of complaints (97% for the top 3: 0.91 vs 0.10).",
         "Deleting the piece ranked as lowering the score raised it in 82% of cases.",
         "Resetting the top-ranked input group to typical values lowered the score in 100% of cases; a random group didn't.",
         "LIME agrees: rank correlation 0.85, same top-3 pieces 77% of the time.",
         "<b>Weak spot:</b> for complaints over 8 pieces the estimate is noisy — a second seed keeps the ranking (rank corr 0.84) "
         "but picks the same top piece only 53% of the time; against the exact answer (5–8 pieces), 16 orders get the top "
         "piece right 84% of the time."])
p("<b>What it shows:</b> across these 200, the words carry 30% of the total effect for paid complaints and 23% for unpaid "
  "ones; the company's own record carries most of the rest. Speed on the Mac: p50 1.7 s, p95 8.4 s per explanation.")
h2("11.3 Serving explanations: a job queue")
p("On the server's 2 cores an explanation takes ~1.4–1.8 s (short complaint), 39–71 s (medium) and ~98 s (long). NGINX "
  "stops waiting after 30 s and two at once would slow everyone, so <font face='Mono' size='8.5'>api/jobs.py</font> hands "
  "out a ticket and runs explanations one at a time (submit → poll → result): same complaint shares a job, finished ones "
  "cached (500), at most 20 waiting, tickets kept 30 min. NGINX limits <i>asking</i> to 4/min per visitor; polling is not "
  "counted. While explaining, /predict from India stays at median 0.69 s.")

# ---------------- 12 Deployment
h1("12. System Architecture and Deployment")
figure(FIG / "system.png", 16.5, "End-to-end architecture: offline data/model pipeline and the online request path.")
h2("12.1 Packaging the model")
bullets(["<b>ONNX export:</b> the network's recipe plus its weights in one file (266 MB); runs on ONNX Runtime with no PyTorch "
         "in the image. Matches PyTorch to 1e-5 (max |Δ logit|); vs the Kaggle T4 fp16 run max |Δp| 0.00036, rank correlation 0.999999.",
         "<b>Bundle:</b> model.onnx, tokenizer.json, preprocessing.json, calibration.json, model_card.json, serving_db.dump and "
         "the three xai_* files — on a GitHub Release, checked by sha256 (deploy/get_model.sh)."])
h2("12.2 Serving database and train/serve skew test")
p("Schema <font face='Mono' size='8.5'>serving</font>: dimension lists, an entity snapshot (company × issue / company / issue / "
  "product rates, shares, trends, quiet days) as of 2025-01-01 built by the same SQL formulas in ~12 s, "
  "<font face='Mono' size='8.5'>serving.model_input()</font> (19 inputs, ~0.06 ms), <font face='Mono' size='8.5'>"
  "serving.clean_narrative()</font>, and the 150,000 test complaints for the demo — 187 MB in Postgres, 57 MB dump. "
  "<b>Skew test:</b> the live track record rebuilt for 3 past days matched training on all 19 inputs (max diff 0) over "
  "20,773 complaints.")
h2("12.3 API and infrastructure")
bullets(["<b>FastAPI</b>: POST /predict (names + text → SQL inputs → clean text → ONNX → Platt → route), GET /complaint/random|{id}, "
         "/options/*, /model-info, /health, POST /explain + GET /explain/jobs/{id}. Input validation: ≥ 20 real words, unknown "
         "company → no-history + note, bad names → 422 with choices.",
         "<b>Docker Compose</b>: postgres:16-alpine restored from the dump on first start (no published port) + api (multi-stage "
         "python:3.11-slim, non-root) + NGINX.",
         "<b>AWS EC2 t4g.small</b> (2 Graviton2 cores, ARM64, 2 GB + swap, Sydney), 20 GB encrypted gp3, Elastic IP; CPU credits "
         "in standard mode (never bills surplus). ≈ $21/month from $140 credits.",
         "<b>NGINX</b>: 403 without the secret header; rate limit 5 req/s per visitor (keyed on Vercel's x-real-ip), body ≤ 64 KB; "
         "<b>Vercel</b> static site (HTML/CSS/JS) forwards API paths with the secret header — same https address, no CORS."])
h2("12.4 Latency (p50 / p95)")
table([["measurement", "MacBook M4", "EC2 server (2 cores)"],
       ["model alone (ONNX, 2 threads, 300 complaints)", "20 / 81 ms", "218 / 803 ms"],
       ["feature lookup serving.model_input", "0.06 ms (in-DB)", "0.6 / 2.9 ms (round trip)"],
       ["API end-to-end /complaint/{id}", "28 / 94 ms", "210 / 807 ms"],
       ["API /predict (short example)", "~41 ms", "82 / 86 ms"],
       ["RAM api / db", "455 / 45 MiB", "~630 MiB (shared reader) / 52 MiB"]],
      [6.6, 3.8, 4.2], "Latency and memory. The feature lookup is under 1 ms, so the model is nearly the whole wait.")
p("Parity through the public link: 200 real complaints vs offline scores, max |Δp| 0.00017, same route 100%.")

# ---------------- 13 Limitations
h1("13. Limitations")
bullets(["It predicts <b>cost to the company, not harm to the customer</b> — no severity label exists.",
         "It knows <i>whether</i> money was paid, not <i>how much</i>; amounts are not published.",
         "The language model can read only the ~1 in 3 complaints whose writers published their story.",
         "Data end on 2024-12-31: new complaints are scored “as of end-2024” until a refresh job exists.",
         "The probability is calibrated on 2024; payouts keep drifting, so it must be recalibrated on new data.",
         "An explanation shows what the model reacted to, not the real reason a company paid; long complaints (> 8 pieces) "
         "have noisy sentence attributions.",
         "Within-company AUC ≈ 0.82 is likely near the ceiling set by unobservable company decisions."])

# ---------------- 14 Conclusion
h1("14. Conclusion and Future Work")
h2("14.1 Conclusion")
p("TriageIQ shows that a fine-tuned DistilBERT fused with leak-proof SQL features ranks complaints by payout risk well "
  "enough to be useful: inside one company's queue it ranks a payout above a non-payout 82% of the time, and the riskiest "
  "10% of complaints contain 92.6% of the payouts. The ablation shows the two modalities are complementary — text wins "
  "inside a company, the track record wins across case types, and fusion is best on every score. The engineering — "
  "point-in-time features, one cleaning function and one feature formula for training and serving, a temporal split, "
  "calibration on the newest data, an exact ONNX export and a faithfulness-tested explainer — matters as much as the "
  "model choice, and every number in this report is reproducible from code in the repository.")
h2("14.2 Future work")
bullets(["<b>Similar-complaint retrieval</b> (pgvector embeddings): show the 5 most similar past complaints and how they ended — in "
         "the original design, not yet built.",
         "<b>Recency-weighted retrain on 2025 data</b>: time-decay sample weights (with its own probability correction), champion vs "
         "challenger against v3.",
         "Weighted loss on all non-payouts instead of undersampling (expected gain modest, +0.005–0.02).",
         "Monitoring: a prediction log and a drift query; CI (lint, tests, image build); a read-only database role.",
         "Expected-cost ranking: P(relief) × claimed amount."])

# ---------------- References
h1("References")
refs = ["Vaswani, A. et al. (2017). Attention Is All You Need. NeurIPS.",
        "Devlin, J. et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. NAACL.",
        "Sanh, V., Debut, L., Chaumond, J., Wolf, T. (2019). DistilBERT, a distilled version of BERT: smaller, faster, cheaper and lighter. arXiv:1910.01108.",
        "Hinton, G., Vinyals, O., Dean, J. (2015). Distilling the Knowledge in a Neural Network. arXiv:1503.02531.",
        "He, P. et al. (2021). DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training. arXiv:2111.09543.",
        "Wu, Y. et al. (2016). Google's Neural Machine Translation System (WordPiece). arXiv:1609.08144.",
        "Howard, J., Ruder, S. (2018). Universal Language Model Fine-tuning for Text Classification (ULMFiT). ACL.",
        "Loshchilov, I., Hutter, F. (2019). Decoupled Weight Decay Regularization (AdamW). ICLR.",
        "Hendrycks, D., Gimpel, K. (2016). Gaussian Error Linear Units (GELUs). arXiv:1606.08415.",
        "Micikevicius, P. et al. (2018). Mixed Precision Training. ICLR.",
        "Guo, C., Berkhahn, F. (2016). Entity Embeddings of Categorical Variables. arXiv:1604.06737.",
        "King, G., Zeng, L. (2001). Logistic Regression in Rare Events Data. Political Analysis.",
        "Chawla, N. et al. (2002). SMOTE: Synthetic Minority Over-sampling Technique. JAIR.",
        "Lin, T.-Y. et al. (2017). Focal Loss for Dense Object Detection. ICCV.",
        "Platt, J. (1999). Probabilistic Outputs for Support Vector Machines. Advances in Large Margin Classifiers.",
        "Guo, C. et al. (2017). On Calibration of Modern Neural Networks. ICML.",
        "Shapley, L. (1953). A Value for n-person Games. Contributions to the Theory of Games.",
        "Lundberg, S., Lee, S.-I. (2017). A Unified Approach to Interpreting Model Predictions (SHAP). NeurIPS.",
        "Ribeiro, M. T., Singh, S., Guestrin, C. (2016). “Why Should I Trust You?” (LIME). KDD.",
        "Huyen, C. (2022). Designing Machine Learning Systems. O'Reilly.",
        "Consumer Financial Protection Bureau. Consumer Complaint Database. consumerfinance.gov/data-research/consumer-complaints."]
for i, r in enumerate(refs, 1):
    story.append(Paragraph(f"[{i}] {r}", ParagraphStyle("ref", parent=BODY, leftIndent=18, firstLineIndent=-18, alignment=0)))

# ---------------- Appendix
h1("Appendix A. The 19 Model Inputs")
table([["#", "column", "what it says", "frame"],
       ["1", "product_id", "product (11 values)", "—"], ["2", "sub_product_id", "sub-product (62)", "—"],
       ["3", "issue_id", "issue (93, renames merged)", "—"], ["4", "state_id", "consumer's state (62)", "—"],
       ["5", "is_older_american", "tagged Older American (62+)", "—"], ["6", "is_servicemember", "tagged servicemember", "—"],
       ["7", "company_no_history", "no known company outcome yet", "outcomes ≥ 60 days old"],
       ["8", "company_issue_no_history", "same, for company × issue", "outcomes ≥ 60 days old"],
       ["9", "company_issue_rate_s", "company's payout rate on this issue, smoothed (K = 5)", "outcomes ≥ 60 days old"],
       ["10", "company_rate_s", "company's overall payout rate, smoothed", "outcomes ≥ 60 days old"],
       ["11", "issue_rate_s", "issue's payout rate across companies, smoothed", "outcomes ≥ 60 days old"],
       ["12", "product_rate_s", "product's payout rate (the smoothing prior)", "outcomes ≥ 60 days old"],
       ["13", "company_untimely_rate", "share of the company's complaints never answered", "outcomes ≥ 60 days old"],
       ["14", "company_share_90d", "company's share of all complaints, last 90 days", "arrivals before today"],
       ["15", "company_issue_share_90d", "company × issue share, last 90 days", "arrivals before today"],
       ["16", "issue_share_90d", "issue's share of all complaints, last 90 days", "arrivals before today"],
       ["17", "company_trend_90d", "ln((last 90 d + 1) / (the 90 before + 1))", "arrivals before today"],
       ["18", "issue_trend_90d", "same, for the issue", "arrivals before today"],
       ["19", "company_quiet_days", "days since the company's previous complaint (log1p)", "order within company"]],
      [0.8, 4.4, 6.6, 3.6], "Model inputs (sql/03_features/feature_dictionary.md). Inputs 1–4 are embedded; 5–19 are the 15 numerics.")
p("<b>Stored but not inputs:</b> company_id (would memorise 4,946 companies and fail on new ones), sub_issue_id (a blank "
  "encodes “filed before Aug 2023”), date_received (the calendar), and the clock counts company_n_prior, "
  "company_tenure_days, days_since_start.")

h1("Appendix B. Technology Stack")
table([["layer", "tools"],
       ["data", "PostgreSQL 16 + pgvector, Docker Compose, SQL window functions, materialized views, pandas, Parquet"],
       ["NLP / ML", "PyTorch, Hugging Face transformers + tokenizers, scikit-learn (TF-IDF, logistic regression, metrics)"],
       ["training compute", "Kaggle free T4 GPU (fp16); MacBook M4 (MPS) for smoke tests"],
       ["serving", "ONNX Runtime (CPU), FastAPI, uvicorn, Pydantic, Docker (multi-stage), NGINX"],
       ["cloud", "AWS EC2 t4g.small (ARM64), Elastic IP, AWS Budgets; Vercel (static site); GitHub Pages (essay); GitHub Releases (model bundle)"],
       ["explainability", "exact and antithetic-sampled Shapley values, LIME (cross-check)"]],
      [3.4, 11.2], "Technology stack.")


# ---------------------------------------------------------------- layout
class Doc(BaseDocTemplate):
    def __init__(self, fn):
        super().__init__(fn, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.2 * cm, bottomMargin=2 * cm,
                         title="TriageIQ — Project Report", author="Shivam Bajaj")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self.decorate)])

    def decorate(self, c, doc):
        if doc.page == 1: return
        c.saveState(); c.setFont("Sans", 7.5); c.setFillColor(MUTED)
        c.drawString(2.2 * cm, A4[1] - 1.4 * cm, "TriageIQ — Project Report")
        c.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, str(doc.page))
        c.setStrokeColor(RULE); c.setLineWidth(0.4); c.line(2.2 * cm, A4[1] - 1.55 * cm, A4[0] - 2.2 * cm, A4[1] - 1.55 * cm)
        c.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            text = f.getPlainText()
            if text == "Table of Contents": return
            level = 0 if f.style.name == "h1" else 1
            key = f"k{id(f)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=True)
            self.notify("TOCEntry", (level, text, self.page, key))


Doc(str(OUT)).multiBuild(story)
print("wrote", OUT)
