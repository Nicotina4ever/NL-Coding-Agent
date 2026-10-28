"""Theme loader — reads theme.tokens.json and generates QSS stylesheet."""
from __future__ import annotations

import json
from pathlib import Path


_TOKENS_PATH = Path(__file__).resolve().parents[2] / "assets" / "theme.tokens.json"


def load_tokens(path: Path | None = None) -> dict:
    p = path or _TOKENS_PATH
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_qss(tokens: dict) -> str:
    b = tokens.get("brand", {})
    n = tokens.get("ui_neutrals", {})
    s = tokens.get("semantic", {})

    ev = b.get("electric_violet", "#7531FE")
    mg = b.get("magenta", "#E4469B")
    dp = b.get("deep_purple", "#521B8D")
    lv = b.get("lavender", "#AB83C6")
    cy = b.get("cyan", "#46A3C0")

    bg   = n.get("background", "#111216")
    sf1  = n.get("surface_1", "#181A20")
    sf2  = n.get("surface_2", "#20232B")
    sf3  = n.get("surface_3", "#292D37")
    bdr  = n.get("border", "#343947")
    tp   = n.get("text_primary", "#F3F4F7")
    ts   = n.get("text_secondary", "#B8BECA")
    tm   = n.get("text_muted", "#7E8798")

    ok   = s.get("success", "#55C58A")
    warn = s.get("warning", "#E6B85C")
    err  = s.get("danger", "#E26472")
    info = s.get("info", "#46A3C0")

    return f"""
/* === NL Coding Agent Theme === */
QWidget {{
    background-color: {bg};
    color: {tp};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}}

QMainWindow {{
    background-color: {bg};
}}

/* Header bar */
#headerBar {{
    background-color: {sf1};
    border-bottom: 1px solid {bdr};
    min-height: 44px;
    max-height: 44px;
}}

#appTitle {{
    color: {tp};
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

#projectLabel {{
    color: {ts};
    font-size: 13px;
}}

#ollamaStatus {{
    color: {tm};
    font-size: 12px;
}}
#ollamaStatus[reachable="true"] {{
    color: {ok};
}}
#ollamaStatus[reachable="false"] {{
    color: {err};
}}

/* Sidebar */
#sidebar {{
    background-color: {sf1};
    border-right: 1px solid {bdr};
    min-width: 160px;
    max-width: 200px;
}}

#sidebarButton {{
    background-color: transparent;
    color: {ts};
    text-align: left;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
}}
#sidebarButton:hover {{
    background-color: {sf2};
    color: {tp};
}}
#sidebarButton:checked {{
    background-color: {sf2};
    color: {ev};
    border-left: 2px solid {ev};
}}

/* Main workspace */
#mainWorkspace {{
    background-color: {bg};
}}

/* Inspector panel */
#inspectorPanel {{
    background-color: {sf1};
    border-left: 1px solid {bdr};
    min-width: 220px;
}}

/* Log panel */
#logPanel {{
    background-color: {sf1};
    border-top: 1px solid {bdr};
    min-height: 120px;
    max-height: 220px;
}}

#logOutput {{
    background-color: {sf1};
    color: {ts};
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    border: none;
    /* NO text-shadow / glow per design rules */
}}

/* Status bar */
#statusBar {{
    background-color: {sf1};
    color: {tm};
    font-size: 11px;
    border-top: 1px solid {bdr};
    padding: 2px 8px;
}}

#vramLabel, #ramLabel, #tasksLabel {{
    color: {tm};
    font-size: 11px;
    padding: 0 6px;
}}

/* Buttons */
QPushButton {{
    background-color: {sf2};
    color: {tp};
    border: 1px solid {bdr};
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {sf3};
    border-color: {ev};
}}
QPushButton:pressed {{
    background-color: {ev};
    color: white;
}}

#primaryButton {{
    background-color: {ev};
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 18px;
    font-weight: 600;
}}
#primaryButton:hover {{
    background-color: {dp};
}}

/* List / Tree widgets */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {sf1};
    color: {tp};
    border: 1px solid {bdr};
    border-radius: 4px;
    alternate-background-color: {sf2};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {ev};
    color: white;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {sf2};
}}

/* Scrollbar */
QScrollBar:vertical {{
    background: {sf1};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {sf3};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ev};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {sf1};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {sf3};
    border-radius: 4px;
    min-width: 24px;
}}

/* Splitter */
QSplitter::handle {{
    background-color: {bdr};
}}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical   {{ height: 2px; }}
QSplitter::handle:hover {{
    background-color: {ev};
}}

/* Labels */
QLabel {{
    color: {tp};
    background: transparent;
}}

/* LineEdit / TextEdit */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {sf2};
    color: {tp};
    border: 1px solid {bdr};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {ev};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ev};
}}

/* ComboBox */
QComboBox {{
    background-color: {sf2};
    color: {tp};
    border: 1px solid {bdr};
    border-radius: 4px;
    padding: 4px 8px;
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background-color: {sf2};
    color: {tp};
    selection-background-color: {ev};
}}

/* Tab widget */
QTabWidget::pane {{
    border: 1px solid {bdr};
    background-color: {sf1};
}}
QTabBar::tab {{
    background-color: {sf1};
    color: {ts};
    padding: 6px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ev};
    border-bottom: 2px solid {ev};
}}
QTabBar::tab:hover {{
    color: {tp};
    background-color: {sf2};
}}

/* Progress bar */
QProgressBar {{
    background-color: {sf2};
    border: 1px solid {bdr};
    border-radius: 4px;
    text-align: center;
    color: {tp};
    height: 8px;
}}
QProgressBar::chunk {{
    background-color: {ev};
    border-radius: 4px;
}}

/* ToolTip */
QToolTip {{
    background-color: {sf3};
    color: {tp};
    border: 1px solid {bdr};
    padding: 4px;
    border-radius: 3px;
}}

/* GroupBox */
QGroupBox {{
    border: 1px solid {bdr};
    border-radius: 4px;
    margin-top: 12px;
    color: {ts};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {ts};
}}
"""


# --- U2 reusable design tokens/components (NL identity only) -----------------
def design_tokens(tokens: dict | None = None) -> dict:
    """Return verified NL token values plus derived typography/spacing scales."""
    values = tokens if tokens is not None else load_tokens()
    b = values.get("brand", {})
    n = values.get("ui_neutrals", {})
    s = values.get("semantic", {})
    return {
        "brand": dict(b), "neutrals": dict(n), "semantic": dict(s),
        "rules": dict(values.get("rules", {})),
        "typography": {"display": "20px", "title": "16px", "section": "13px",
                       "body": "13px", "small": "12px", "micro": "11px",
                       "mono": "12px"},
        "spacing": {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24},
        "density": {"row": 26, "card_min_height": 64, "header_height": 44},
        "radius": {"sm": 3, "md": 4, "lg": 6},
    }


def component_qss(tokens: dict) -> str:
    """Component rules derived only from the verified NL palette (no new colours)."""
    b = tokens.get("brand", {})
    n = tokens.get("ui_neutrals", {})
    s = tokens.get("semantic", {})
    ev = b.get("electric_violet", "#7531FE")
    lv = b.get("lavender", "#AB83C6")
    cy = b.get("cyan", "#46A3C0")
    sf1 = n.get("surface_1", "#181A20")
    sf2 = n.get("surface_2", "#20232B")
    sf3 = n.get("surface_3", "#292D37")
    bdr = n.get("border", "#343947")
    tp = n.get("text_primary", "#F3F4F7")
    ts = n.get("text_secondary", "#B8BECA")
    tm = n.get("text_muted", "#7E8798")
    ok = s.get("success", "#55C58A")
    warn = s.get("warning", "#E6B85C")
    err = s.get("danger", "#E26472")
    return f"""
/* U2 component rules - typography, spacing/density, cards and badges */
#nlSectionHeader {{ background: transparent; }}
#nlSectionTitle {{ color: {tp}; font-size: 16px; font-weight: 700; letter-spacing: 0.2px; }}
#nlSectionSubtitle {{ color: {tm}; font-size: 12px; }}
#nlSectionRule {{ color: {bdr}; }}
#nlSummaryCard {{ background-color: {sf1}; border: 1px solid {bdr};
                  border-radius: 6px; padding: 8px 10px; min-height: 64px; }}
#nlSummaryCard:hover {{ border-color: {ev}; background-color: {sf2}; }}
#nlCardTitle {{ color: {tm}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }}
#nlCardValue {{ color: {tp}; font-size: 14px; font-weight: 600; }}
#nlCardDetail {{ color: {ts}; font-size: 12px; }}
#nlStatusBadge {{ border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 700; }}
#nlStatusBadge[tone="ok"] {{ color: {ok}; background-color: rgba(85,197,138,0.12); }}
#nlStatusBadge[tone="warn"] {{ color: {warn}; background-color: rgba(230,184,92,0.12); }}
#nlStatusBadge[tone="error"] {{ color: {err}; background-color: rgba(226,100,114,0.12); }}
#nlStatusBadge[tone="info"] {{ color: {cy}; background-color: rgba(70,163,192,0.12); }}
#nlStatusBadge[tone="idle"] {{ color: {tm}; background-color: {sf2}; }}
#nlStatusBadge[tone="accent"] {{ color: {ev}; background-color: rgba(117,49,254,0.14); }}
#nlEmptyState {{ color: {tm}; font-size: 12px; padding: 10px; }}
#nlActivityBadge {{ color: {cy}; font-size: 11px; font-weight: 600; padding: 2px 8px;
                    border: 1px solid {bdr}; border-radius: 8px; }}
#nlActivityBadge[state="running"] {{ color: {ok}; border-color: {ok}; }}
#nlActivityBadge[state="blocked"] {{ color: {err}; border-color: {err}; }}
#nlProjectIdentity {{ color: {lv}; font-size: 12px; }}
#subtleLinkButton {{ background: transparent; color: {tm}; border: none;
                     padding: 2px 4px; font-size: 11px; text-align: right; }}
#subtleLinkButton:hover {{ color: {ev}; }}
"""


def apply_theme(app, tokens_path: Path | None = None) -> str:
    tokens = load_tokens(tokens_path)
    qss = build_qss(tokens) + component_qss(tokens)
    app.setStyleSheet(qss)
    return qss
