"""Custom agent configuration dialog for NL Coding Agent presets."""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from nl_coding_agent.gui.components import section_header


class _EditDialog(QDialog):
    def __init__(self, agent: dict | None = None, parent=None, *, models: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Custom agent")
        self.resize(520, 560)
        self._agent = dict(agent or {})
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(str(self._agent.get("name") or ""))
        self._name.setAccessibleName("Custom agent name")
        form.addRow("Name", self._name)
        self._provider = QComboBox()
        for value in ("ollama", "openai_compatible"):
            self._provider.addItem(value, value)
        self._provider.setCurrentText(str(self._agent.get("provider") or "ollama"))
        self._provider.setAccessibleName("Custom agent provider")
        form.addRow("Provider", self._provider)
        self._model = QLineEdit(str(self._agent.get("model") or ""))
        self._model.setAccessibleName("Custom agent model")
        if models:
            self._model.setPlaceholderText(", ".join(models[:4]))
        form.addRow("Model", self._model)
        self._role = QLineEdit(str(self._agent.get("role") or "assistant"))
        self._role.setAccessibleName("Custom agent role")
        form.addRow("Role", self._role)
        self._instructions = QPlainTextEdit(str(self._agent.get("instructions") or ""))
        self._instructions.setAccessibleName("Custom agent instructions")
        self._instructions.setMinimumHeight(120)
        form.addRow("Instructions", self._instructions)
        self._tools = QLineEdit(", ".join(self._agent.get("tools") or []))
        self._tools.setAccessibleName("Enabled tools")
        self._tools.setPlaceholderText("read, edit, terminal")
        form.addRow("Tools", self._tools)
        self._permissions = QLineEdit(", ".join(self._agent.get("permissions") or []))
        self._permissions.setAccessibleName("Permissions")
        self._permissions.setPlaceholderText("read-only, project-write")
        form.addRow("Permissions", self._permissions)
        self._enabled = QCheckBox("Enabled")
        self._enabled.setChecked(bool(self._agent.get("enabled", True)))
        self._enabled.setAccessibleName("Custom agent enabled")
        form.addRow("Enabled", self._enabled)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        ok = QPushButton("Save")
        ok.setObjectName("primaryButton")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip() or "Custom agent",
            "provider": self._provider.currentText(),
            "model": self._model.text().strip(),
            "role": self._role.text().strip() or "assistant",
            "instructions": self._instructions.toPlainText().strip(),
            "tools": [item.strip() for item in self._tools.text().split(",") if item.strip()],
            "permissions": [item.strip() for item in self._permissions.text().split(",") if item.strip()],
            "enabled": self._enabled.isChecked(),
        }


class CustomAgentsDialog(QDialog):
    def __init__(self, services, parent=None):
        super().__init__(parent)
        self._services = services
        self.setWindowTitle("Custom agents")
        self.resize(680, 480)
        self.setAccessibleName("Custom agents configuration")
        layout = QVBoxLayout(self)
        layout.addWidget(section_header("CUSTOM AGENTS",
                                       "Treat predefined agents as presets."))
        self._list = QListWidget()
        self._list.setAccessibleName("Configured custom agents")
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        new_btn = QPushButton("New")
        new_btn.setObjectName("primaryButton")
        new_btn.clicked.connect(self._new)
        row.addWidget(new_btn)
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("secondaryButton")
        edit_btn.clicked.connect(self._edit)
        row.addWidget(edit_btn)
        dup_btn = QPushButton("Duplicate")
        dup_btn.setObjectName("secondaryButton")
        dup_btn.clicked.connect(self._duplicate)
        row.addWidget(dup_btn)
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._delete)
        row.addWidget(delete_btn)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)
        self._refresh()

    def _ids(self) -> list[str]:
        return [str(self._list.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(self._list.count())]

    def _selected_id(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _refresh(self) -> None:
        self._list.clear()
        for agent in self._services.list_custom_agents():
            item = QListWidgetItem(str(agent.get("name") or "Custom agent"))
            item.setData(Qt.ItemDataRole.UserRole, agent.get("id"))
            self._list.addItem(item)

    def _new(self) -> None:
        dialog = _EditDialog(parent=self, models=["qwen3.5:9b"])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._services.create_custom_agent(dialog.values().pop("name"), **dialog.values())
        self._refresh()

    def _edit(self) -> None:
        agent_id = self._selected_id()
        if agent_id is None:
            return
        agent = self._services.get_custom_agent(agent_id)
        if agent is None:
            return
        dialog = _EditDialog(agent, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self._services.update_custom_agent(agent_id, **values)
        self._refresh()

    def _duplicate(self) -> None:
        agent_id = self._selected_id()
        if agent_id is None:
            return
        self._services.duplicate_custom_agent(agent_id)
        self._refresh()

    def _delete(self) -> None:
        agent_id = self._selected_id()
        if agent_id is None:
            return
        answer = QMessageBox.question(
            self, "Delete custom agent", "Delete selected custom agent?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._services.delete_custom_agent(agent_id)
        self._refresh()