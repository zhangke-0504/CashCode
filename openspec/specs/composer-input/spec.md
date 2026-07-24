## ADDED Requirements

### Requirement: Text input with send action
The system SHALL provide a multi-line text input that submits on Enter (Shift+Enter for newline).

#### Scenario: User sends message with Enter
- **WHEN** user types a message and presses Enter (without Shift)
- **THEN** message is submitted and the input field is cleared

#### Scenario: Multi-line with Shift+Enter
- **WHEN** user presses Shift+Enter
- **THEN** a newline is inserted in the input without submitting

#### Scenario: Empty message not sent
- **WHEN** user presses Enter with an empty or whitespace-only input
- **THEN** nothing is sent and the input remains focused

### Requirement: Send button
The system SHALL display a Send button that triggers message submission.

#### Scenario: Send button click
- **WHEN** user clicks the Send button with non-empty input
- **THEN** message is sent, input is cleared, and button becomes disabled until response is complete

### Requirement: Stop button during generation
The system SHALL replace the Send button with a Stop button while the assistant is generating a response.

#### Scenario: Generation in progress
- **WHEN** the assistant is actively generating (after user message sent, before `done` event)
- **THEN** the Send button is replaced by a Stop button

#### Scenario: Stop clicked
- **WHEN** user clicks Stop
- **THEN** cancel frame is sent over WebSocket and the button reverts to Send

### Requirement: Auto-focus on session switch
The system SHALL focus the Composer input when the user switches to a different session.

#### Scenario: Session switch
- **WHEN** user clicks a session in the sidebar
- **THEN** the Composer textarea gains focus automatically
