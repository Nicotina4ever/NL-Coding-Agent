# External source references

## Code - OSS: inspected revision, 2026-10-29

Repository: <https://github.com/microsoft/vscode>. GitHub REST API returned main
revision **aaf0914f8bafb3d011b9f13b8ec0123d81cef5fe**. Directory metadata and the
selected files below were read at that revision using the contents API, including
file blob hashes. No repository clone, dependencies, installation or build occurred.
Selected response bodies/evidence are cached under
`.workspace/cache/references/vscode/<revision>/`; acquisition summaries are
`.workspace/temp/vscode-{source-access,relevant-sources,mcp-sources}.jsonl`.

The [upstream README](https://github.com/microsoft/vscode/blob/aaf0914f8bafb3d011b9f13b8ec0123d81cef5fe/README.md)
distinguishes MIT Code - OSS source from the Microsoft-specific VS Code distribution.
The inspected license is `LICENSE.txt`. `package.json` identifies `code-oss-dev`
1.145.0; `.npmrc` specifies an Electron runtime target of 43.8.3 and native builds.
These observations describe this pinned checkout, not the locally installed VS Code.

| Reuse category | Inspected source and dependency evidence | Decision against NL's current implementation |
|---|---|---|
| 1. Direct open-source code | `LICENSE.txt`, `package.json`; individual source modules carry MIT headers. Platform utilities still import `base/common` and other TypeScript modules. | No upstream code copied. There is no demonstrated benefit from translating or embedding those utilities instead of existing Python/Qt services. Assets/code would require a specific need and retained attribution. |
| 2. Adaptable patterns | `src/vs/workbench/browser/workbench.ts` extends `Layout` and receives services; `browser/layout.ts` uses `SerializableGrid`, `LayoutStateModel` and storage. `browser/parts/editor/editorPart.ts` owns editor groups and serializes their grid. | Reuse NL's `StudioWorkspace`/`QDockWidget`, editor tabs and Qt state restoration. Keep project context in `MainWindow` and operations in `AppServices`; do not recreate VS Code's DI container. |
| 3. Public extension/protocol integration | `src/vscode-dts/vscode.d.ts`: MCP definitions around lines 20510–20552, `lm.registerTool` at 20780, `lm.registerMcpServerDefinitionProvider` at 20844. `src/vs/workbench/api/common/extHost.api.impl.ts` routes these APIs to extension-host actors. | An external MCP server can expose the existing NL mission engine; a future extension could register its definition/tools using these public APIs. A Chat Participant is not needed for this bridge. No extension is installed or implemented by this inspection. |
| 4. Code - OSS/browser/Electron components | `src/vs/editor/browser/widget/codeEditor/codeEditorWidget.ts` imports DOM, CSS, rendering/configuration, model and instantiation services. Workbench editor/layout import browser grids and platform services; native shell configuration is in `.npmrc`. | Monaco/workbench code cannot be inserted as a native Qt editor. Web embedding or a Code - OSS/Electron client would be a separate integration with real dependencies; neither is justified by the current task. Keep NL's working editor. |

Additional service boundaries inspected:

- `src/vs/platform/instantiation/common/instantiation.ts` and
  `instantiationService.ts`: service identifiers, collections, dependency graph,
  child service lifetime/disposal. These are patterns, not a Python dependency.
- `src/vs/workbench/services/extensions/common/extensions.ts`: extension-host
  protocol, activation, dependency and host-kind contracts; extensions do not obtain
  arbitrary direct workbench implementation access through the public API.
- `src/vs/workbench/contrib/mcp/common/mcpRegistryTypes.ts`,
  `mcpServerConnection.ts`, `mcpService.ts`, `mcpConfiguration.ts`: registry/trust,
  connection state, transport, tool/service and configuration responsibilities.
  These implementation files depend on VS Code's internal services and are not
  reused by NL. NL's existing `app/mcp.py`, permissions, events and official Python
  MCP SDK remain the integration points.

Public configuration documentation inspected:
[VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers).
An MCP configuration example must name the actual NL runtime/launcher/project paths;
writing an example does not install it into VS Code or grant execution permission.
A partial clone outside NL's repository remains unnecessary. Obtain owner approval
if future source investigation actually requires one.
