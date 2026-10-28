"""Reusable NL Studio UI components (U2).

All styling is derived from the verified assets/theme.tokens.json palette through
theme.design_tokens/component_qss. Components never introduce unrelated colours,
glow on text/code/logs, or business logic.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from .theme import design_tokens


def _tokens():
    try:
        return design_tokens()
    except Exception:  # noqa: BLE001 - components remain usable in isolation
        return {}


def section_header(title: str, subtitle: str = "", *, parent=None) -> QWidget:
    box = QWidget(parent)
    box.setObjectName("nlSectionHeader")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    heading = QLabel(str(title))
    heading.setObjectName("nlSectionTitle")
    heading.setAccessibleName(str(title))
    layout.addWidget(heading)
    if subtitle:
        sub = QLabel(str(subtitle))
        sub.setObjectName("nlSectionSubtitle")
        sub.setWordWrap(True)
        sub.setAccessibleName(str(subtitle))
        layout.addWidget(sub)
    return box


def summary_card(title: str, value: str, detail: str = "", *,
                 accessible_name: str = "", parent=None) -> QFrame:
    card = QFrame(parent)
    card.setObjectName("nlSummaryCard")
    card.setAccessibleName(accessible_name or (title + ": " + value))
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(2)
    title_label = QLabel(str(title).upper())
    title_label.setObjectName("nlCardTitle")
    title_label.setWordWrap(True)
    title_label.setMinimumWidth(0)
    title_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                              QSizePolicy.Policy.Preferred)
    value_label = QLabel(str(value))
    value_label.setObjectName("nlCardValue")
    value_label.setWordWrap(True)
    value_label.setMinimumWidth(0)
    value_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                              QSizePolicy.Policy.Preferred)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    if detail:
        detail_label = QLabel(str(detail))
        detail_label.setObjectName("nlCardDetail")
        detail_label.setWordWrap(True)
        detail_label.setMinimumWidth(0)
        detail_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Preferred)
        layout.addWidget(detail_label)
    return card


def status_badge(text: str, tone: str = "info", *, parent=None) -> QLabel:
    allowed = {"ok", "warn", "error", "info", "idle", "accent"}
    badge = QLabel(str(text))
    badge.setObjectName("nlStatusBadge")
    badge.setProperty("tone", tone if tone in allowed else "info")
    badge.setAccessibleName(str(text))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return badge


def empty_state(text: str, *, parent=None) -> QLabel:
    label = QLabel(str(text))
    label.setObjectName("nlEmptyState")
    label.setWordWrap(True)
    label.setAccessibleName(str(text))
    return label


def card_row(cards, *, parent=None) -> QWidget:
    row = QWidget(parent)
    row.setObjectName("nlCardRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for card in cards:
        layout.addWidget(card, 1)
    return row
