"""Design tokens and CSS for the JagaPaip command centre.

Selectors target Streamlit's stable data-testid attributes and the
``st-key-*`` classes produced by keyed containers, not generated class names.
"""

NAVY = "#14283F"
NAVY_DARK = "#0B1929"
TEAL = "#14B8A6"
TEAL_DEEP = "#0D9488"
BG = "#F5F7FA"
CARD = "#FFFFFF"
INK = "#172B3A"
MUTED = "#64748B"
BORDER = "#E2E8F0"
RED = "#C2410C"
RISK_RED = "#B91C1C"
AMBER = "#B45309"
GREEN = "#047857"

CSS = f"""
<style>
:root {{
  --jp-navy: {NAVY};
  --jp-navy-dark: {NAVY_DARK};
  --jp-teal: {TEAL};
  --jp-teal-deep: {TEAL_DEEP};
  --jp-bg: {BG};
  --jp-card: {CARD};
  --jp-ink: {INK};
  --jp-muted: {MUTED};
  --jp-border: {BORDER};
  --jp-radius: 10px;
  --jp-shadow: 0 1px 2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.04);
}}

/* Workspace */
.stApp {{ background: var(--jp-bg); color: var(--jp-ink); }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}
[data-testid="stMainBlockContainer"] {{
  max-width: 1320px;
  padding: 2.2rem 2.4rem 3rem 2.4rem;
}}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {{ gap: 1rem; }}
h1, h2, h3 {{ color: var(--jp-ink); letter-spacing: -0.01em; }}
[data-testid="stHeaderActionElements"] {{ display: none; }}

/* Sidebar */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, var(--jp-navy-dark) 0%, var(--jp-navy) 100%);
  border-right: 1px solid #0A1622;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding: 0.5rem 1.1rem 2rem 1.1rem; }}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 0.65rem; }}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ color: #DCE5EF; }}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{ color: #93A4B8; font-size: 0.82rem; line-height: 1.45; }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255, 255, 255, 0.08); margin: 0.6rem 0; }}
section[data-testid="stSidebar"] [data-testid="stSliderThumbValue"],
section[data-testid="stSidebar"] [data-testid="stSliderTickBar"] div {{ color: #DCE5EF; }}
section[data-testid="stSidebar"] [data-testid="stTooltipIcon"] svg {{ stroke: #93A4B8; }}

.jp-brand {{ display: flex; gap: 12px; align-items: center; padding: 0.2rem 0 0.9rem 0; }}
.jp-mark {{
  width: 38px; height: 38px; border-radius: 9px; flex: none;
  background: var(--jp-teal); color: var(--jp-navy-dark);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 0.95rem; letter-spacing: 0.02em;
}}
.jp-name {{ color: #FFFFFF; font-size: 1.2rem; font-weight: 700; line-height: 1.15; }}
.jp-tag {{ color: #93A4B8; font-size: 0.84rem; margin-top: 2px; }}
.jp-side-label {{
  color: #7F93A8; font-size: 0.74rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; margin: 0.4rem 0 0.1rem 0;
}}

/* Sidebar navigation: radio options rendered as menu items */
section[data-testid="stSidebar"] [data-testid="stRadio"],
section[data-testid="stSidebar"] [data-testid="stRadio"] > div,
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {{ width: 100%; }}
section[data-testid="stSidebar"] [data-testid="stRadioGroup"] {{ align-items: stretch; width: 100%; }}
section[data-testid="stSidebar"] [data-testid="stRadioGroup"] > div {{ width: 100%; gap: 2px; display: flex; flex-direction: column; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
  display: flex; box-sizing: border-box;
  width: 100%; margin: 0; padding: 0.55rem 0.75rem;
  border-radius: 8px; border-left: 3px solid transparent;
  cursor: pointer; transition: background 120ms ease;
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{
  color: #B6C4D3; font-size: 0.93rem; font-weight: 500;
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background: rgba(255, 255, 255, 0.05); }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:has(input:checked) {{
  background: rgba(20, 184, 166, 0.14);
  border-left-color: var(--jp-teal);
}}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:has(input:checked) p {{ color: #FFFFFF; font-weight: 650; }}

.jp-side-stats {{
  background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px; padding: 0.6rem 0.75rem;
}}
.jp-side-row {{ display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; font-size: 0.84rem; }}
.jp-side-row span {{ color: #93A4B8; }}
.jp-side-row strong {{ color: #F1F5F9; font-weight: 600; font-variant-numeric: tabular-nums; }}
.jp-side-status {{ display: flex; gap: 8px; align-items: flex-start; font-size: 0.86rem; color: #DCE5EF; line-height: 1.4; }}
.jp-side-status .dot {{ margin-top: 6px; }}

/* Page header */
.jp-header {{ padding-bottom: 1.1rem; border-bottom: 1px solid var(--jp-border); margin-bottom: 0.2rem; }}
.jp-header h1 {{ font-size: 1.85rem; font-weight: 700; margin: 0; padding: 0; line-height: 1.2; }}
.jp-subtitle {{ color: var(--jp-muted); font-size: 1rem; margin: 0.35rem 0 0 0; max-width: 820px; line-height: 1.5; }}
.jp-chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 0.85rem; }}

.chip {{
  display: inline-flex; align-items: center; gap: 7px; white-space: nowrap;
  padding: 5px 11px; border-radius: 999px; font-size: 0.82rem; font-weight: 600;
  background: var(--jp-card); color: var(--jp-ink); border: 1px solid var(--jp-border);
}}
.chip.demo {{ background: #FFF7ED; color: #9A3412; border-color: #FED7AA; }}
.chip.live {{ background: #F0FDFA; color: #115E59; border-color: #99F6E4; }}
.chip .muted {{ color: var(--jp-muted); font-weight: 500; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }}
.dot.teal {{ background: var(--jp-teal); }}
.dot.amber {{ background: #F59E0B; }}
.dot.red {{ background: #DC2626; }}
.dot.green {{ background: #10B981; }}
.dot.slate {{ background: #94A3B8; }}

/* KPI cards */
.jp-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }}
.jp-kpi {{
  background: var(--jp-card); border: 1px solid var(--jp-border); border-radius: var(--jp-radius);
  box-shadow: var(--jp-shadow); padding: 1rem 1.15rem 1.05rem 1.15rem; min-width: 0;
}}
.jp-kpi .label {{ color: var(--jp-muted); font-size: 0.86rem; font-weight: 600; display: flex; align-items: center; gap: 7px; }}
.jp-kpi .value {{
  color: var(--jp-ink); font-size: 1.85rem; font-weight: 700; line-height: 1.15;
  margin-top: 0.45rem; font-variant-numeric: tabular-nums; letter-spacing: -0.01em;
}}
.jp-kpi .value.unavailable {{ color: #94A3B8; font-size: 1.3rem; font-weight: 600; }}
.jp-kpi .value small {{ font-size: 0.95rem; font-weight: 600; color: var(--jp-muted); margin-left: 3px; }}
.jp-kpi .note {{ color: var(--jp-muted); font-size: 0.84rem; margin-top: 0.35rem; line-height: 1.4; }}

/* Panels: keyed st.container(key="panel_...") */
[class*="st-key-panel"] {{
  background: var(--jp-card); border: 1px solid var(--jp-border); border-radius: var(--jp-radius);
  box-shadow: var(--jp-shadow); padding: 1.1rem 1.2rem 1.15rem 1.2rem;
}}
[class*="st-key-panel"] [data-testid="stVerticalBlock"] {{ gap: 0.75rem; }}
.jp-panel-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
.jp-panel-title {{ color: var(--jp-ink); font-size: 1.05rem; font-weight: 700; margin: 0; }}
.jp-panel-sub {{ color: var(--jp-muted); font-size: 0.88rem; margin: 0.2rem 0 0 0; line-height: 1.45; }}
.jp-panel-meta {{ color: var(--jp-muted); font-size: 0.84rem; white-space: nowrap; }}

/* Notices */
.jp-notice {{
  display: flex; gap: 12px; align-items: flex-start;
  background: var(--jp-card); border: 1px solid var(--jp-border); border-left: 4px solid var(--jp-teal);
  border-radius: var(--jp-radius); padding: 0.85rem 1rem; color: var(--jp-ink); font-size: 0.92rem; line-height: 1.5;
}}
.jp-notice.warn {{ border-left-color: #F59E0B; background: #FFFBF5; }}
.jp-notice strong {{ font-weight: 650; }}
.jp-notice ul {{ margin: 0.3rem 0 0 0; padding-left: 1.1rem; }}
.jp-notice li {{ margin: 0.15rem 0; color: #334155; }}

/* Fact lists */
.jp-fact {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid #EEF2F6; padding: 0.5rem 0; font-size: 0.92rem; }}
.jp-fact:last-child {{ border-bottom: none; }}
.jp-fact span {{ color: var(--jp-muted); }}
.jp-fact strong {{ color: var(--jp-ink); font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }}

/* Pills */
.pill {{ display: inline-block; border-radius: 6px; padding: 2px 8px; font-size: 0.8rem; font-weight: 650; white-space: nowrap; }}
.pill.high {{ background: #FEF2F2; color: #B91C1C; }}
.pill.moderate {{ background: #FFFBEB; color: #B45309; }}
.pill.low {{ background: #ECFDF5; color: #047857; }}
.pill.teal {{ background: #F0FDFA; color: #0F766E; }}
.pill.slate {{ background: #F1F5F9; color: #475569; }}

/* Budget meter */
.jp-meter {{ height: 10px; background: #EEF2F6; border-radius: 999px; overflow: hidden; }}
.jp-meter > div {{ height: 100%; background: var(--jp-teal-deep); border-radius: 999px; }}
.jp-meter-labels {{ display: flex; justify-content: space-between; font-size: 0.82rem; color: var(--jp-muted); margin-top: 6px; }}
.jp-big {{ font-size: 1.6rem; font-weight: 700; color: var(--jp-ink); font-variant-numeric: tabular-nums; line-height: 1.1; }}
.jp-big small {{ font-size: 0.9rem; color: var(--jp-muted); font-weight: 600; }}
.jp-action-row {{ display: flex; align-items: center; justify-content: space-between; padding: 0.42rem 0; border-bottom: 1px solid #EEF2F6; font-size: 0.92rem; }}
.jp-action-row:last-child {{ border-bottom: none; }}
.jp-action-row .name {{ display: flex; align-items: center; gap: 9px; color: var(--jp-ink); }}
.jp-action-row .count {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.jp-action-row .count small {{ color: var(--jp-muted); font-weight: 500; margin-left: 6px; }}

/* Priority table (HTML, Overview) */
.jp-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin: 0; display: table; }}
.jp-table th, .jp-table td {{ border-left: none !important; border-right: none !important; border-top: none !important; }}
.jp-table th {{
  text-align: left; color: var(--jp-muted); font-weight: 600; font-size: 0.8rem;
  padding: 0.55rem 0.7rem; border-bottom: 1px solid var(--jp-border); background: #F8FAFC; white-space: nowrap;
}}
.jp-table td {{ padding: 0.62rem 0.7rem; border-bottom: 1px solid #EEF2F6; color: var(--jp-ink); vertical-align: middle; }}
.jp-table tr:last-child td {{ border-bottom: none; }}
.jp-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.jp-table .rank {{ color: var(--jp-muted); font-weight: 600; width: 44px; }}
.jp-table .pipe {{ font-weight: 650; }}
.jp-table .sub {{ color: var(--jp-muted); font-size: 0.8rem; }}
.jp-score {{ display: flex; align-items: center; gap: 8px; justify-content: flex-end; }}
.jp-score .bar {{ width: 64px; height: 6px; background: #EEF2F6; border-radius: 999px; overflow: hidden; }}
.jp-score .bar > div {{ height: 100%; border-radius: 999px; }}
.jp-table-wrap {{ overflow-x: auto; }}

/* Native widgets on the light workspace */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p {{ color: #334155; font-weight: 600; font-size: 0.88rem; }}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {{ color: var(--jp-muted); font-size: 0.86rem; }}
[data-testid="stMain"] [data-testid="stDataFrame"] {{ border: 1px solid var(--jp-border); border-radius: 8px; overflow: hidden; }}
[data-testid="stMain"] [data-testid="stExpander"] details {{ background: var(--jp-card); border: 1px solid var(--jp-border); border-radius: var(--jp-radius); }}
[data-testid="stMain"] [data-testid="stMetric"] {{
  background: var(--jp-card); border: 1px solid var(--jp-border); border-radius: var(--jp-radius);
  padding: 0.85rem 1rem; box-shadow: var(--jp-shadow);
}}
[data-testid="stMain"] [data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}

.jp-step {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%; margin-right: 8px;
  background: var(--jp-navy); color: #FFFFFF; font-size: 0.8rem; font-weight: 700;
}}
.jp-foot {{ color: var(--jp-muted); font-size: 0.82rem; }}

@media (max-width: 1100px) {{
  .jp-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 640px) {{
  .jp-kpis {{ grid-template-columns: 1fr; }}
  [data-testid="stMainBlockContainer"] {{ padding: 1.5rem 1rem 2rem 1rem; }}
}}
</style>
"""
