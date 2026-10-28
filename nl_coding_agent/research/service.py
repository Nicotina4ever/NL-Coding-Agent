"""Research service: routing + fetch + reader + store behind the permission boundary.

Stage 7 research R4 (NL-BP-170/174/175/205/207). The service is the only entry
point that combines provider routing, safe fetch, reader, GitHub/Hugging Face
investigators and the local research store.

Boundary contract:
  * before any network-capable operation the service calls
    permissions.check_capability and auto_review.evaluate_action;
  * normal policy outcomes are returned as explicit NeedsApproval/Denied results,
    not raised past the boundary;
  * no fetch or investigator transport exists by default: callers must inject
    explicit transport(s); provider search is declarative/offline unless a real
    provider adapter is injected;
  * retrieved provenance (canonical URL, redirects, timestamps, content hash,
    title/metadata, bounded excerpt, scope links, citations) is persisted in the
    research store; secrets are never logged or included in results;
  * no cloud/model call or silent network fallback is implemented.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from nl_coding_agent.core import auto_review, permissions

from .fetch import FetchDenied, FetchError, Fetcher, RetrievalPolicy, Transport
from .injection import (
    MAX_WARNINGS,
    InjectionScan,
    combine_scans,
    scan_payload,
    scan_text,
)
from .github import GitHubError, GitHubResearchClient
from .huggingface import HuggingFaceError, HuggingFaceResearchClient
from .providers import (
    ProviderRegistry,
    RoutingPolicy,
    SearchQuery,
    default_registry,
    route,
)
from .reader import UnsupportedDocument, read_document
from .store import MAX_EXCERPT_CHARS, ResearchStore, ResearchStoreError

OUTCOME_ALLOWED = "allowed"
OUTCOME_NEEDS_APPROVAL = "needs_approval"
OUTCOME_DENIED = "denied"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_ERROR = "error"

CAPABILITY_BY_OPERATION = {
    "search": permissions.CAPABILITY_WEB_SEARCH,
    "fetch_read": permissions.CAPABILITY_WEB_FETCH,
    "github_lookup": permissions.CAPABILITY_WEB_FETCH,
    "huggingface_lookup": permissions.CAPABILITY_WEB_FETCH,
    "download": permissions.CAPABILITY_DOWNLOAD,
    "model_inference_local": permissions.CAPABILITY_MODEL_INFERENCE_LOCAL,
    "model_inference_cloud": permissions.CAPABILITY_MODEL_INFERENCE_CLOUD,
}
NETWORK_OPERATIONS = ("search", "fetch_read", "github_lookup", "huggingface_lookup")
GITHUB_ACTIONS = ("repository", "readme", "license", "branches", "tags",
                  "commits", "issues", "issue_comments", "pull_requests",
                  "pull_reviews", "releases", "workflows", "file_contents",
                  "search_repositories")
GITHUB_METHODS = {
    "repository": "repository", "readme": "readme", "license": "license_info",
    "branches": "branches", "tags": "tags", "commits": "commits",
    "issues": "issues", "issue_comments": "issue_comments",
    "pull_requests": "pull_requests", "pull_reviews": "pull_reviews",
    "releases": "releases", "workflows": "workflows",
    "file_contents": "file_contents", "search_repositories": "search_repositories",
}
HF_ACTIONS = ("search_models", "search_datasets", "search_spaces", "model_info",
              "dataset_info", "space_info", "model_card", "files", "license_info")
HF_METHODS = {name: name for name in HF_ACTIONS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _decision_dict(value) -> dict:
    if hasattr(value, "to_dict"):
        try:
            data = value.to_dict()
            if isinstance(data, dict):
                return dict(data)
        except Exception:
            pass
    if isinstance(value, Mapping):
        return dict(value)
    return {"outcome": str(getattr(value, "outcome", "denied")),
            "reason": str(getattr(value, "reason", "no decision")),
            "capability": str(getattr(value, "capability", ""))}


def _decision_outcome(value) -> str:
    if isinstance(value, Mapping):
        return str(value.get("outcome") or "").lower()
    return str(getattr(value, "outcome", "") or "").lower()


@dataclass(frozen=True, slots=True)
class ResearchResult:
    operation: str
    capability: str
    outcome: str
    reason: str = ""
    boundary: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome == OUTCOME_ALLOWED

    @property
    def needs_approval(self) -> bool:
        return self.outcome == OUTCOME_NEEDS_APPROVAL

    @property
    def denied(self) -> bool:
        return self.outcome == OUTCOME_DENIED

    @property
    def error(self) -> bool:
        return self.outcome in (OUTCOME_ERROR, OUTCOME_UNAVAILABLE)

    def to_dict(self) -> dict:
        return {"operation": self.operation, "capability": self.capability,
                "outcome": self.outcome, "allowed": self.allowed,
                "needs_approval": self.needs_approval, "denied": self.denied,
                "error": self.error, "reason": self.reason,
                "boundary": dict(self.boundary), "payload": dict(self.payload)}


class ResearchService:
    """Permission-bounded facade over provider routing, fetch, reader and store."""

    def __init__(self, *, registry: ProviderRegistry | None = None,
                 store: ResearchStore | None = None,
                 policy: RetrievalPolicy | None = None,
                 fetch_transport: Transport | None = None,
                 http_transport=None,
                 github_client=None, huggingface_client=None,
                 permission_checker: Callable | None = None,
                 auto_reviewer: Callable | None = None,
                 profile: str = auto_review.PROFILE_MANUAL,
                 controls: Mapping | None = None,
                 github_token: str | None = None,
                 huggingface_token: str | None = None,
                 store_path=None) -> None:
        self.registry = registry if registry is not None else default_registry()
        self.store = store if store is not None else ResearchStore(store_path)
        self.policy = policy if policy is not None else RetrievalPolicy()
        self._fetch_transport = fetch_transport
        self._http_transport = http_transport
        self._github_client = github_client
        self._huggingface_client = huggingface_client
        self._permission_checker = permission_checker or permissions.check_capability
        self._auto_reviewer = auto_reviewer or auto_review.evaluate_action
        self.profile = str(profile or auto_review.PROFILE_MANUAL)
        self.controls = dict(controls or {})
        self._github_token = str(github_token or "").strip()
        self._huggingface_token = str(huggingface_token or "").strip()

    def __repr__(self) -> str:
        return ("ResearchService(profile=" + repr(self.profile)
                + ", providers=" + str(len(self.registry.provider_ids()))
                + ", transport=" + ("injected" if self._fetch_transport else "none")
                + ", http_transport=" + ("injected" if self._http_transport else "none")
                + ", tokens=REDACTED)")

    # -------------------------------------------------------- injection scan
    @staticmethod
    def _scan_injection(values, *, source: str = "") -> InjectionScan:
        """Scan bounded untrusted values without executing/evaluating anything."""
        scans = []
        for label, value in values:
            if value in (None, ""):
                continue
            if isinstance(value, (str, bytes)):
                scans.append(scan_text(value, source=source + "." + label))
            else:
                scans.append(scan_payload(value, source=source + "." + label))
        return combine_scans(scans)

    @staticmethod
    def _injection_summary(scan: InjectionScan) -> dict:
        return {"count": scan.count, "kinds": list(scan.kinds),
                "highest_severity": scan.highest_severity,
                "scanned_chars": scan.scanned_chars,
                "truncated": bool(scan.truncated),
                "content_sha256": scan.content_sha256, "untrusted": True}

    def _audit_injection(self, operation: str, scan: InjectionScan, *,
                         canonical_url: str = "", ref: str = "",
                         source_id: int | None = None,
                         project_id: int | None = None,
                         mission_id: int | None = None) -> None:
        if not scan.has_signals:
            return
        try:
            from nl_coding_agent.persistence.database import init_db, log_event
            conn = init_db()
            try:
                for signal in scan.signals[:20]:
                    payload = {
                        "url": str(canonical_url or "")[:2000],
                        "ref": str(source_id if source_id is not None
                                   else ref or "")[:500],
                        "sha256": signal.sha256,
                        "hash": signal.sha256,
                        "kind": signal.kind,
                    }
                    log_event(
                        conn,
                        "Untrusted research content contained instruction-like text",
                        source="research", payload=json.dumps(payload,
                                                              ensure_ascii=False,
                                                              sort_keys=True),
                        project_id=project_id, mission_id=mission_id,
                        event_kind="research_injection")
            finally:
                conn.close()
        except Exception:
            # Audit persistence must not turn a successful read into an error.
            pass

    # ------------------------------------------------------------- boundary
    def capability_for_operation(self, operation: str) -> str:
        capability = CAPABILITY_BY_OPERATION.get(str(operation))
        if capability is None:
            raise ValueError("unknown research operation: " + repr(operation))
        return capability

    def _scope(self, operation: str, capability: str, *, project_id=None,
               mission_id=None, task_id=None, url: str | None = None,
               host: str | None = None) -> permissions.CapabilityScope:
        context = {"project_id": project_id}
        if capability == permissions.CAPABILITY_WEB_FETCH and url:
            return permissions.CapabilityScope(
                permissions.SCOPE_EXTERNAL_RESOURCE, _safe_text(url, 2000), project_id)
        if capability == permissions.CAPABILITY_WEB_SEARCH:
            return permissions.CapabilityScope(
                permissions.SCOPE_PROJECT,
                str(project_id) if project_id is not None else "research-search",
                project_id)
        if project_id is not None:
            return permissions.CapabilityScope(permissions.SCOPE_PROJECT,
                                               str(project_id), project_id)
        return permissions.CapabilityScope(permissions.SCOPE_EXTERNAL_RESOURCE,
                                           host or operation, None)

    def authorize(self, operation: str, *, project_id: int | None = None,
                  mission_id: int | None = None, task_id: int | None = None,
                  url: str | None = None, host: str | None = None,
                  tool: str = "") -> tuple[ResearchResult, dict]:
        capability = self.capability_for_operation(operation)
        scope = self._scope(operation, capability, project_id=project_id,
                            mission_id=mission_id, task_id=task_id, url=url, host=host)
        context = {"project_id": project_id, "mission_id": mission_id,
                   "task_id": task_id, "operation": operation}
        try:
            permission_decision = self._permission_checker(capability, scope, context)
        except Exception as exc:
            permission_decision = permissions.Denied(
                capability, "permission checker failed closed: " + type(exc).__name__,
                scope_kind=scope.kind, scope_value=scope.value, project_id=project_id)
        permission_data = _decision_dict(permission_decision)
        action = auto_review.ActionDescriptor(
            capability=capability, scope_kind=scope.kind, scope_value=scope.value,
            tool=_safe_text(tool or operation), host=_safe_text(host or "", 255),
            context=dict(context))
        try:
            review_decision = self._auto_reviewer(
                action, self.profile, controls=dict(self.controls) or None)
            review_data = _decision_dict(review_decision)
            review_outcome = _decision_outcome(review_decision)
            review_data.setdefault(
                "auto_approved", review_outcome == auto_review.OUTCOME_AUTO_APPROVED)
            review_data.setdefault(
                "needs_human_approval",
                review_outcome == auto_review.OUTCOME_NEEDS_HUMAN_APPROVAL)
            review_data.setdefault("denied", review_outcome == auto_review.OUTCOME_DENIED)
        except Exception as exc:
            review_data = {"outcome": auto_review.OUTCOME_DENIED,
                           "reason": "auto-review failed closed: " + type(exc).__name__}
            review_outcome = auto_review.OUTCOME_DENIED
        permission_outcome = _decision_outcome(permission_decision)
        if permission_outcome == permissions.OUTCOME_DENIED or \
                review_outcome == auto_review.OUTCOME_DENIED:
            outcome = OUTCOME_DENIED
        elif permission_outcome == permissions.OUTCOME_NEEDS_APPROVAL or \
                review_outcome == auto_review.OUTCOME_NEEDS_HUMAN_APPROVAL:
            outcome = OUTCOME_NEEDS_APPROVAL
        elif permission_outcome == permissions.OUTCOME_ALLOWED and \
                review_outcome == auto_review.OUTCOME_AUTO_APPROVED:
            outcome = OUTCOME_ALLOWED
        else:
            outcome = OUTCOME_NEEDS_APPROVAL
        reason_parts = []
        if permission_data.get("reason"):
            reason_parts.append("permission: " + str(permission_data["reason"]))
        if review_data.get("reason"):
            reason_parts.append("auto-review: " + str(review_data["reason"]))
        boundary = {"capability": capability, "outcome": outcome,
                    "permission": permission_data, "auto_review": review_data,
                    "scope_kind": scope.kind, "scope_value": scope.value}
        result = ResearchResult(operation=operation, capability=capability,
                                outcome=outcome, reason="; ".join(reason_parts),
                                boundary=boundary)
        return result, boundary

    # --------------------------------------------------------------- search
    def search(self, query: str, *, search_type: str = "web",
               provider: str | None = None,
               routing_policy: RoutingPolicy | None = None,
               max_results: int = 10, project_id: int | None = None,
               mission_id: int | None = None, task_id: int | None = None) -> ResearchResult:
        boundary_result, _boundary = self.authorize(
            "search", project_id=project_id, mission_id=mission_id,
            task_id=task_id, tool="web_search")
        if not boundary_result.allowed:
            return boundary_result
        try:
            query_obj = SearchQuery(query, search_type, max_results=max_results)
        except Exception as exc:
            return self._error("search", boundary_result.capability, exc, boundary_result)
        decision = route(self.registry, query_obj, routing_policy or RoutingPolicy(),
                         preferred_provider=provider)
        if not decision.available or not decision.selected_provider:
            return ResearchResult(
                operation="search", capability=boundary_result.capability,
                outcome=OUTCOME_UNAVAILABLE,
                reason="no eligible provider: " + decision.status.reason,
                boundary=boundary_result.boundary,
                payload={"routing": decision.as_dict()})
        provider_impl = self.registry.provider(decision.selected_provider)
        if provider_impl is None:
            return ResearchResult(
                operation="search", capability=boundary_result.capability,
                outcome=OUTCOME_UNAVAILABLE,
                reason="selected provider has no executable adapter",
                boundary=boundary_result.boundary,
                payload={"routing": decision.as_dict()})
        try:
            response = provider_impl.search(query_obj)
        except Exception as exc:
            return self._error("search", boundary_result.capability, exc,
                               boundary_result,
                               payload={"routing": decision.as_dict()})
        if not response.status.available:
            return ResearchResult(
                operation="search", capability=boundary_result.capability,
                outcome=OUTCOME_UNAVAILABLE,
                reason=response.status.reason,
                boundary=boundary_result.boundary,
                payload={"routing": decision.as_dict(),
                         "provider_status": response.status.as_dict()})
        results = [item.as_dict() for item in response.results]
        scans = []
        for item in results:
            item_url = str(item.get("url") or "search")
            item_scan = scan_payload(item, source=item_url)
            if item_scan.has_signals:
                self._audit_injection("search", item_scan,
                                      canonical_url=item_url, ref=str(query),
                                      project_id=project_id,
                                      mission_id=mission_id)
            scans.append(item_scan)
        scan = combine_scans(scans)
        return ResearchResult(
            operation="search", capability=boundary_result.capability,
            outcome=OUTCOME_ALLOWED, reason="",
            boundary=boundary_result.boundary,
            payload={"routing": decision.as_dict(),
                     "provider_status": response.status.as_dict(),
                     "results": results,
                     "untrusted": True,
                     "injection_warnings": scan.warnings(MAX_WARNINGS),
                     "injection_scan": self._injection_summary(scan)})

    # --------------------------------------------------------------- fetch
    def fetch_read(self, url: str, *, project_id: int | None = None,
                   mission_id: int | None = None, task_id: int | None = None,
                   headers: Mapping[str, str] | None = None) -> ResearchResult:
        if self._fetch_transport is None:
            return ResearchResult(
                operation="fetch_read", capability=permissions.CAPABILITY_WEB_FETCH,
                outcome=OUTCOME_UNAVAILABLE,
                reason="no explicit fetch transport injected; no default network transport exists")
        captured: list[ResearchResult] = []

        def permission_gate(target_url: str) -> bool:
            from urllib.parse import urlsplit
            try:
                host = urlsplit(target_url).hostname or ""
            except Exception:
                host = ""
            gate_result, _ = self.authorize(
                "fetch_read", project_id=project_id, mission_id=mission_id,
                task_id=task_id, url=target_url, host=host, tool="web_fetch")
            captured.append(gate_result)
            return gate_result.allowed

        fetcher = Fetcher(policy=self.policy, transport=self._fetch_transport,
                          permission_gate=permission_gate)
        try:
            document = fetcher.fetch(url, headers=headers)
        except FetchDenied as exc:
            last = captured[-1] if captured else None
            if last is not None and not last.allowed:
                return last
            return ResearchResult(
                operation="fetch_read", capability=permissions.CAPABILITY_WEB_FETCH,
                outcome=OUTCOME_DENIED,
                reason="fetch policy denied: " + str(exc.reason),
                boundary=(captured[-1].boundary if captured else {}))
        except FetchError as exc:
            return ResearchResult(
                operation="fetch_read", capability=permissions.CAPABILITY_WEB_FETCH,
                outcome=OUTCOME_ERROR,
                reason="fetch failed: " + str(exc.reason),
                boundary=(captured[-1].boundary if captured else {}))
        try:
            page = read_document(document)
        except Exception as exc:
            return self._error("fetch_read", permissions.CAPABILITY_WEB_FETCH, exc,
                               captured[-1] if captured else None)
        excerpt = ""
        title = ""
        if isinstance(page, UnsupportedDocument):
            excerpt = ""
            title = document.title or document.canonical_url
            supported = False
            page_payload = page.to_dict()
        else:
            excerpt = str(page.text or "")[:MAX_EXCERPT_CHARS]
            title = str(page.title or document.title or document.canonical_url)
            supported = True
            page_payload = {"kind": page.kind, "title": page.title,
                            "text": page.text, "markdown": page.markdown,
                            "truncated": page.truncated, "untrusted": True,
                            "removed": list(page.removed)}
        scan_values = [("html", document.content), ("title", title)]
        if not isinstance(page, UnsupportedDocument):
            scan_values.extend([("text", page.text), ("markdown", page.markdown),
                                ("metadata", dict(page.metadata))])
        scan = self._scan_injection(scan_values,
                                    source=document.canonical_url)
        try:
            saved = self.store.save_source(
                document.canonical_url, requested_url=document.source.requested_url,
                final_url=document.source.final_url,
                redirect_chain=document.source.redirect_chain,
                excerpt=excerpt, title=title, provider="web-fetch",
                content_sha256=document.sha256, content_type=document.source.content_type,
                size_bytes=document.size, metadata=(dict(page.metadata)
                    if not isinstance(page, UnsupportedDocument) else {}),
                retrieved_at=document.source.fetched_at, project_id=project_id,
                mission_id=mission_id, task_id=task_id, confidence=0.8)
            citation = self.store.save_citation(saved["id"], quote="",
                                                locator="", note="fetched web source")
        except ResearchStoreError as exc:
            return self._error("fetch_read", permissions.CAPABILITY_WEB_FETCH, exc,
                               captured[-1] if captured else None)
        provenance = document.source.provenance.to_dict()
        self._audit_injection("fetch_read", scan,
                              canonical_url=document.canonical_url,
                              ref=str(saved["id"]), source_id=saved["id"],
                              project_id=project_id, mission_id=mission_id)
        warnings = scan.warnings(MAX_WARNINGS)
        if isinstance(page_payload, dict):
            page_payload["injection_warnings"] = warnings
        return ResearchResult(
            operation="fetch_read", capability=permissions.CAPABILITY_WEB_FETCH,
            outcome=OUTCOME_ALLOWED, boundary=(captured[-1].boundary if captured else {}),
            payload={"source_id": saved["id"], "citation_id": citation["id"],
                     "canonical_url": document.canonical_url,
                     "title": title, "supported": supported,
                     "page": page_payload, "provenance": provenance,
                     "untrusted": True,
                     "injection_warnings": warnings,
                     "injection_scan": self._injection_summary(scan)})

    # ----------------------------------------------------------- investigators
    def _github(self):
        if self._github_client is not None:
            return self._github_client
        if self._http_transport is None:
            raise ResearchStoreError("no explicit HTTP transport injected for GitHub")
        self._github_client = GitHubResearchClient(
            self._http_transport, token=self._github_token or None, env={})
        return self._github_client

    def _huggingface(self):
        if self._huggingface_client is not None:
            return self._huggingface_client
        if self._http_transport is None:
            raise ResearchStoreError("no explicit HTTP transport injected for Hugging Face")
        self._huggingface_client = HuggingFaceResearchClient(
            self._http_transport, token=self._huggingface_token or None, env={})
        return self._huggingface_client

    def _investigator_result(self, operation: str, tool: str, action: str,
                             result, boundary_result: ResearchResult, *,
                             project_id=None, mission_id=None,
                             task_id=None) -> ResearchResult:
        if not boundary_result.allowed:
            return boundary_result
        try:
            result_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        except Exception as exc:
            return self._error(operation, boundary_result.capability, exc, boundary_result)
        saved = None
        citation = None
        canonical_url = str((result_dict.get("provenance") or {}).get(
            "canonical_url") or "")
        scan = self._scan_injection([("result", result_dict)],
                                    source=canonical_url or operation)
        try:
            provenance = result_dict.get("provenance") or {}
            canonical_url = str(provenance.get("canonical_url") or "")
            if canonical_url:
                excerpt = json.dumps(result_dict.get("data"), ensure_ascii=False)[:MAX_EXCERPT_CHARS]
                title = (str((result_dict.get("data") or {}).get("full_name")
                             or (result_dict.get("data") or {}).get("repo_id")
                             or result_dict.get("kind") or operation))
                saved = self.store.save_source(
                    canonical_url, excerpt=excerpt, title=title,
                    provider=operation.replace("_lookup", ""),
                    content_type="application/json",
                    metadata={"kind": str(result_dict.get("kind") or "")},
                    retrieved_at=provenance.get("fetched_at"),
                    project_id=project_id, mission_id=mission_id,
                    task_id=task_id, confidence=0.7)
                citation = self.store.save_citation(
                    saved["id"], note=operation + " read-only investigator result")
        except ResearchStoreError as exc:
            return self._error(operation, boundary_result.capability, exc, boundary_result)
        self._audit_injection(operation, scan, canonical_url=canonical_url,
                              ref=str(saved["id"] if saved else ""),
                              source_id=saved["id"] if saved else None,
                              project_id=project_id, mission_id=mission_id)
        return ResearchResult(operation=operation, capability=boundary_result.capability,
                              outcome=OUTCOME_ALLOWED,
                              boundary=boundary_result.boundary,
                              payload={"action": action, "result": result_dict,
                                       "source_id": saved["id"] if saved else None,
                                       "citation_id": citation["id"] if citation else None,
                                       "untrusted": True,
                                       "injection_warnings": scan.warnings(MAX_WARNINGS),
                                       "injection_scan": self._injection_summary(scan)})

    def github_lookup(self, *, action: str = "repository",
                      full_name: str | None = None, query: str | None = None,
                      path: str | None = None, ref: str | None = None,
                      number: int | None = None, state: str = "open",
                      limit: int = 20, project_id=None, mission_id=None,
                      task_id=None) -> ResearchResult:
        if action not in GITHUB_ACTIONS:
            return ResearchResult(
                operation="github_lookup", capability=permissions.CAPABILITY_WEB_FETCH,
                outcome=OUTCOME_DENIED, reason="unsupported GitHub action: " + str(action))
        boundary_result, _ = self.authorize(
            "github_lookup", project_id=project_id, mission_id=mission_id,
            task_id=task_id, url="https://api.github.com/", host="api.github.com",
            tool="github_lookup")
        if not boundary_result.allowed:
            return boundary_result
        try:
            client = self._github()
            if action in ("search_repositories",):
                if not query:
                    raise ValueError("query is required")
                result = client.search_repositories(query, limit=limit)
            elif action in ("file_contents",):
                if not full_name or not path:
                    raise ValueError("full_name and path are required")
                result = client.file_contents(full_name, path, ref=ref)
            elif action in ("issue_comments", "pull_reviews"):
                if not full_name or number is None:
                    raise ValueError("full_name and number are required")
                method = getattr(client, GITHUB_METHODS[action])
                result = (method(full_name, number, limit=limit)
                          if action == "issue_comments" else method(full_name, number))
            elif action in ("issues", "pull_requests"):
                if not full_name:
                    raise ValueError("full_name is required")
                result = getattr(client, GITHUB_METHODS[action])(
                    full_name, state=state, limit=limit)
            else:
                if not full_name:
                    raise ValueError("full_name is required")
                method = getattr(client, GITHUB_METHODS[action])
                if action in ("repository",):
                    result = method(full_name)
                elif action in ("readme", "license", "commits"):
                    result = method(full_name, ref=ref)
                else:
                    result = method(full_name, limit=limit)
        except (GitHubError, ValueError, ResearchStoreError) as exc:
            return self._error("github_lookup", boundary_result.capability, exc,
                               boundary_result)
        except Exception as exc:
            return self._error("github_lookup", boundary_result.capability, exc,
                               boundary_result)
        return self._investigator_result("github_lookup", "github_lookup", action,
                                         result, boundary_result,
                                         project_id=project_id,
                                         mission_id=mission_id, task_id=task_id)

    def huggingface_lookup(self, *, action: str = "search_models",
                           query: str | None = None, repo_id: str | None = None,
                           revision: str | None = None, limit: int = 20,
                           project_id=None, mission_id=None,
                           task_id=None) -> ResearchResult:
        if action not in HF_ACTIONS:
            return ResearchResult(
                operation="huggingface_lookup",
                capability=permissions.CAPABILITY_WEB_FETCH,
                outcome=OUTCOME_DENIED, reason="unsupported Hugging Face action: "
                + str(action))
        boundary_result, _ = self.authorize(
            "huggingface_lookup", project_id=project_id, mission_id=mission_id,
            task_id=task_id, url="https://huggingface.co/", host="huggingface.co",
            tool="huggingface_lookup")
        if not boundary_result.allowed:
            return boundary_result
        try:
            client = self._huggingface()
            method = getattr(client, HF_METHODS[action])
            if action.startswith("search_"):
                if not query:
                    raise ValueError("query is required")
                result = method(query, limit=limit)
            elif action in ("license_info",):
                if not repo_id:
                    raise ValueError("repo_id is required")
                result = method(repo_id)
            else:
                if not repo_id:
                    raise ValueError("repo_id is required")
                result = method(repo_id, revision=revision)
        except (HuggingFaceError, ValueError, ResearchStoreError) as exc:
            return self._error("huggingface_lookup", boundary_result.capability,
                               exc, boundary_result)
        except Exception as exc:
            return self._error("huggingface_lookup", boundary_result.capability,
                               exc, boundary_result)
        return self._investigator_result("huggingface_lookup", "huggingface_lookup",
                                         action, result, boundary_result,
                                         project_id=project_id,
                                         mission_id=mission_id, task_id=task_id)

    # --------------------------------------------------------------- store
    def save_finding(self, question: str, answer: str = "", *, source_ids: Sequence[int] = (),
                     confidence: float = 0.5, project_id=None, mission_id=None,
                     task_id=None, metadata: Mapping | None = None) -> ResearchResult:
        try:
            saved = self.store.save_finding(
                question, answer, source_ids=source_ids, confidence=confidence,
                project_id=project_id, mission_id=mission_id, task_id=task_id,
                metadata=metadata)
        except ResearchStoreError as exc:
            return self._error("save_finding", "read", exc, None)
        return ResearchResult(operation="save_finding", capability="read",
                              outcome=OUTCOME_ALLOWED,
                              payload={"finding_id": saved["id"],
                                       "created": saved.get("created", False),
                                       "deduped": saved.get("deduped", False)})

    def list_findings(self, *, project_id=None, mission_id=None, task_id=None,
                      text: str | None = None, include_stale: bool = True,
                      limit: int = 50, offset: int = 0) -> ResearchResult:
        try:
            rows = self.store.list_findings(
                project_id=project_id, mission_id=mission_id, task_id=task_id,
                text=text, include_stale=include_stale, limit=limit, offset=offset)
        except ResearchStoreError as exc:
            return self._error("list_findings", "read", exc, None)
        return ResearchResult(operation="list_findings", capability="read",
                              outcome=OUTCOME_ALLOWED, payload={"findings": rows})

    def search_saved(self, text: str, *, project_id=None, mission_id=None,
                     task_id=None, include_stale: bool = True,
                     limit: int = 50, offset: int = 0) -> ResearchResult:
        try:
            sources = self.store.search_sources(
                text, project_id=project_id, mission_id=mission_id, task_id=task_id,
                include_stale=include_stale, limit=limit, offset=offset)
            findings = self.store.list_findings(
                project_id=project_id, mission_id=mission_id, task_id=task_id,
                text=text, include_stale=include_stale, limit=limit, offset=offset)
        except ResearchStoreError as exc:
            return self._error("search_saved", "read", exc, None)
        return ResearchResult(operation="search_saved", capability="read",
                              outcome=OUTCOME_ALLOWED,
                              payload={"sources": sources, "findings": findings})

    def mark_stale(self, *, source_id: int | None = None,
                   finding_id: int | None = None, reason: str = "") -> ResearchResult:
        try:
            changed = []
            if source_id is not None:
                changed.append({"source_id": source_id,
                                "changed": self.store.mark_source_stale(source_id, reason)})
            if finding_id is not None:
                changed.append({"finding_id": finding_id,
                                "changed": self.store.mark_finding_stale(finding_id, reason)})
        except ResearchStoreError as exc:
            return self._error("mark_stale", "read", exc, None)
        return ResearchResult(operation="mark_stale", capability="read",
                              outcome=OUTCOME_ALLOWED, payload={"changed": changed})

    def refresh_source(self, source_id: int, *, excerpt: str | None = None,
                       content_sha256: str | None = None) -> ResearchResult:
        try:
            row = self.store.refresh_source(source_id, excerpt=excerpt,
                                            content_sha256=content_sha256)
        except ResearchStoreError as exc:
            return self._error("refresh_source", "read", exc, None)
        if row is None:
            return ResearchResult(operation="refresh_source", capability="read",
                                  outcome=OUTCOME_ERROR, reason="source not found")
        return ResearchResult(operation="refresh_source", capability="read",
                              outcome=OUTCOME_ALLOWED, payload={"source": row})

    # --------------------------------------------------------------- helpers
    def _error(self, operation: str, capability: str, exc: Exception,
               boundary_result: ResearchResult | None,
               payload: Mapping | None = None) -> ResearchResult:
        return ResearchResult(
            operation=operation, capability=capability, outcome=OUTCOME_ERROR,
            reason=type(exc).__name__ + ": " + str(exc),
            boundary=(boundary_result.boundary if boundary_result else {}),
            payload=dict(payload or {}))
