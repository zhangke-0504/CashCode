## ADDED Requirements

### Requirement: Navigate to the Skill market
The sidebar SHALL provide a `Skill 市场` navigation button separate from conversation creation, the MCP market, and history expansion.

#### Scenario: User opens Skill market
- **WHEN** the user activates `Skill 市场`
- **THEN** the main area renders the Skill market while preserving the active chat attachment and history expansion state

#### Scenario: Skill market navigation is active
- **WHEN** the Skill market is the current main view
- **THEN** its sidebar navigation row is visually identified as the current page without highlighting the MCP market

#### Scenario: User returns to a conversation from Skill market
- **WHEN** the Skill market is open and the user selects a history row or creates a new conversation
- **THEN** the application switches to chat view and attaches or creates the requested session
