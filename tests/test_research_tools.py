"""Tests for typed read-only research tool descriptors (no execution, no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl_coding_agent.core import permissions  # noqa: E402
from nl_coding_agent.research import tools  # noqa: E402


class DescriptorTests(unittest.TestCase):
    def test_descriptors_are_unique_typed_and_read_only(self):
        names = [item.name for item in tools.RESEARCH_TOOL_DESCRIPTORS]
        self.assertEqual(sorted(names), sorted(tools.READ_ONLY_TOOL_NAMES))
        self.assertEqual(len(names), len(set(names)))
        for item in tools.RESEARCH_TOOL_DESCRIPTORS:
            self.assertTrue(item.read_only)
            self.assertTrue(item.network)
            self.assertTrue(item.requires_citation)
            self.assertTrue(item.provenance_required)
            self.assertIn(item.capability, permissions.CAPABILITIES)
            self.assertTrue(item.input_schema.get("type") == "object")
            self.assertTrue(item.output_schema.get("type") == "object")
            self.assertIn("outcome", item.output_schema["required"])
            descriptor = item.describe()
            self.assertEqual(descriptor["read_only"], True)
            self.assertNotIn("write", item.name.lower())
            self.assertNotIn("download", item.name.lower())

    def test_capability_and_scope_mapping(self):
        search = tools.research_tool("web_search")
        self.assertEqual(search.capability, permissions.CAPABILITY_WEB_SEARCH)
        self.assertEqual(search.scope_kind, permissions.SCOPE_PROJECT)
        fetch = tools.research_tool("web_fetch")
        self.assertEqual(fetch.capability, permissions.CAPABILITY_WEB_FETCH)
        self.assertEqual(fetch.scope_kind, permissions.SCOPE_EXTERNAL_RESOURCE)
        for name in ("github_lookup", "huggingface_lookup"):
            item = tools.research_tool(name)
            self.assertEqual(item.capability, permissions.CAPABILITY_WEB_FETCH)
            self.assertEqual(item.scope_kind, permissions.SCOPE_EXTERNAL_RESOURCE)
        self.assertIsNone(tools.research_tool("write_file"))
        self.assertIsNone(tools.research_tool("download"))
        self.assertIsNone(tools.research_tool("publish_release"))

    def test_schemas_are_bounded_and_explicit(self):
        fetch = tools.research_tool("web_fetch")
        self.assertEqual(fetch.input_schema["required"], ["url"])
        self.assertFalse(fetch.input_schema["additionalProperties"])
        self.assertIn("pattern", fetch.input_schema["properties"]["url"])
        search = tools.research_tool("web_search")
        self.assertEqual(search.input_schema["required"], ["query"])
        self.assertLessEqual(search.input_schema["properties"]["max_results"]["maximum"], 100)
        github = tools.research_tool("github_lookup")
        self.assertIn("search_repositories", github.input_schema["properties"]["action"]["enum"])
        self.assertIn("contents", github.input_schema["properties"]["action"]["enum"])
        hf = tools.research_tool("huggingface_lookup")
        self.assertIn("search_models", hf.input_schema["properties"]["action"]["enum"])


class RegistryTests(unittest.TestCase):
    def test_typed_registry_rejects_duplicates_and_lists_descriptors(self):
        registry = tools.ResearchToolRegistry()
        for descriptor in tools.RESEARCH_TOOL_DESCRIPTORS:
            registry.register(descriptor)
        self.assertEqual(len(registry), 4)
        self.assertIn("web_search", registry)
        self.assertEqual(len(registry.describe_all()), 4)
        with self.assertRaises(tools.ResearchToolError):
            registry.register(tools.RESEARCH_TOOL_DESCRIPTORS[0])
        with self.assertRaises(tools.ResearchToolError):
            registry.register({"name": "not-a-descriptor"})

    def test_register_function_supports_new_dict_and_list_targets(self):
        created = tools.register_research_tools()
        self.assertIsInstance(created, tools.ResearchToolRegistry)
        self.assertEqual(len(created), 4)
        mapping = {}
        tools.register_research_tools(mapping)
        self.assertEqual(sorted(mapping), sorted(tools.READ_ONLY_TOOL_NAMES))
        with self.assertRaises(tools.ResearchToolError):
            tools.register_research_tools(mapping)
        items = []
        tools.register_research_tools(items)
        self.assertEqual(len(items), 4)
        self.assertEqual(len(tools.describe_research_tools()), 4)

    def test_forbidden_descriptor_tokens_are_rejected(self):
        with self.assertRaises(tools.ResearchToolError):
            tools.ResearchToolDescriptor(
                name="publish_release", description="bad",
                capability=permissions.CAPABILITY_WEB_FETCH,
                scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
                input_schema={"type": "object"}, output_schema={"type": "object"})
        with self.assertRaises(tools.ResearchToolError):
            tools.ResearchToolDescriptor(
                name="web_fetch", description="bad",
                capability="unknown-capability",
                scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
                input_schema={"type": "object"}, output_schema={"type": "object"})
        with self.assertRaises(tools.ResearchToolError):
            tools.ResearchToolDescriptor(
                name="web_fetch", description="bad",
                capability=permissions.CAPABILITY_WEB_FETCH,
                scope_kind=permissions.SCOPE_EXTERNAL_RESOURCE,
                input_schema={"type": "object"}, output_schema={"type": "object"},
                read_only=False)


class StaticGuardTests(unittest.TestCase):
    def test_tools_module_has_no_execution_network_or_model_import(self):
        source = (REPO_ROOT / "nl_coding_agent" / "research" / "tools.py").read_text(
            encoding="utf-8")
        for forbidden in ("import urllib", "import requests", "import socket",
                          "import subprocess", "http.client", "os.system(",
                          "ollama", "crewai", "model.run", "urlopen("):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertIn("ResearchToolDescriptor", source)
        self.assertIn("read_only", source)
        self.assertIn("no write", source.lower())
        names = [item.name for item in tools.RESEARCH_TOOL_DESCRIPTORS]
        for forbidden in ("write", "install", "publish", "upload", "download",
                          "push", "delete"):
            self.assertFalse(any(forbidden in name for name in names))


if __name__ == "__main__":
    unittest.main()
