## ADDED Requirements

### Requirement: Navigate to LLM settings from a bottom settings menu
The sidebar SHALL pin a `设置` control with a gear icon below the scrollable session history and SHALL open an upward menu containing an `LLM 设置` command.

#### Scenario: User opens the settings menu
- **WHEN** the user activates the bottom `设置` control
- **THEN** an upward menu appears above the control with `LLM 设置` as its only current item and the control exposes its expanded state accessibly

#### Scenario: User opens LLM settings
- **WHEN** the user activates `LLM 设置`
- **THEN** the application closes the menu, renders the LLM settings view in the main area, and preserves the active chat and session history state

#### Scenario: User dismisses the settings menu
- **WHEN** the menu is open and the user presses Escape, clicks outside it, or activates the settings control again
- **THEN** the menu closes without changing the current main view

#### Scenario: User opens LLM settings on mobile
- **WHEN** the mobile sidebar is open and the user activates `LLM 设置`
- **THEN** the application renders the settings view and closes the mobile sidebar overlay

