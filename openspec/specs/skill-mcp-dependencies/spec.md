# Skill MCP Dependencies Specification

## Purpose
Define structured Skill dependencies and safe lazy preparation of required and optional MCP capabilities.

## Requirements

### Requirement: Skill dependencies use structured declarations
The system SHALL parse required and optional built-in tool, MCP server, binary, and environment dependencies from validated Skill metadata and SHALL treat those declarations as the activation authority.

#### Scenario: Body contains undeclared MCP-looking text
- **WHEN** Skill content mentions an `mcp_*`-shaped name that is not declared
- **THEN** the system may report a diagnostic but does not activate or connect the dependency based only on that text

### Requirement: Required MCP dependencies are prepared at load time
The system SHALL prepare declared required MCP servers through the existing lazy connection mechanism and activate their declared tools before the next model iteration.

#### Scenario: Required cached MCP server is not connected
- **WHEN** an available Skill with that required server is loaded
- **THEN** the server connects it, registers its tools, activates the declared tools, and exposes them in the next ReAct iteration of the same turn

#### Scenario: Required MCP preparation fails
- **WHEN** a required MCP server cannot connect, list tools, or provide a declared tool
- **THEN** Skill loading returns a dependency error and does not report a successful load

### Requirement: Optional MCP dependencies remain deferred
The system SHALL report optional MCP dependencies without connecting them during Skill loading.

#### Scenario: Loaded Skill declares an optional server
- **WHEN** the Skill is loaded and its workflow has not requested the optional capability
- **THEN** the optional server remains disconnected and can later be prepared through the normal MCP lazy-loading path

### Requirement: Skill loading never executes dependency scripts
The system SHALL NOT execute scripts, install binaries, modify environment variables, authenticate services, or call domain MCP tools merely because a Skill was loaded.

#### Scenario: Skill package includes scripts
- **WHEN** the Skill is searched or loaded
- **THEN** scripts remain inert until an authorized normal tool call explicitly executes one
