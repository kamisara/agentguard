# Sprint 1 – Manual AI Provenance Capture

**Project:** AgentGuard

**Sprint Duration:** Sprint 1

**Status:** Completed

---

# Objective

The objective of Sprint 1 is to validate the most fundamental assumption behind AgentGuard:

> AI generation events can be represented as structured provenance metadata before entering a software repository.

At this stage, the goal is **not** to provide cryptographic guarantees, CI/CD integration, or anomaly detection.

Instead, Sprint 1 focuses exclusively on designing and recording the contextual information associated with an AI-assisted code generation event.

---

# Problem Statement

Modern version control systems such as Git record:

- Source code
- Commit history
- Authors
- Branches
- File modifications

However, Git does **not** record:

- Which AI model generated the code
- The prompt given to the AI
- The developer's original intent
- Whether a human reviewed the generated output
- The context surrounding AI-assisted development

As a result, once code is committed, the software supply chain loses visibility into the AI generation process.

Sprint 1 demonstrates that this missing context can be captured independently of Git.

---

# Scope

Sprint 1 intentionally excludes:

- Digital signatures
- Cryptographic verification
- Sigstore
- Cosign
- Rekor
- in-toto
- CI/CD integration
- Machine Learning
- Behavioral analysis
- Policy enforcement

These components will be implemented in later sprints.

---

# Functional Overview

The prototype simulates a single AI-assisted coding interaction.

The workflow is:

```
Developer

↓

Uses AI

↓

AgentGuard records metadata

↓

Creates a Contextual Attestation

↓

Stores the attestation as JSON
```

The current implementation uses manual user input to simulate an AI interaction.

Automatic metadata collection will be introduced in Sprint 2.

---

# Contextual Attestation Schema (Version 1)

Each captured interaction produces a JSON document with the following structure:

| Field | Description |
|---------|-------------|
| schema_version | Version of the attestation schema |
| attestation_id | Unique identifier for the attestation |
| timestamp | UTC time when the event was recorded |
| developer_intent | The developer's original objective |
| prompt | Prompt sent to the AI |
| agent_identity | AI provider and model information |
| ai_output_summary | Brief description of the generated output |
| human_review_status | Indicates whether the generated output was reviewed |

Example:

```json
{
  "schema_version": "1.0.0",
  "attestation_id": "...",
  "timestamp": "...",
  "developer_intent": "...",
  "prompt": "...",
  "agent_identity": {
    "provider": "...",
    "model": "..."
  },
  "ai_output_summary": "...",
  "human_review_status": {
    "reviewed": false,
    "reviewer": null
  }
}
```

---

# Design Decisions

## JSON

JSON was selected because it is:

- Human readable
- Language independent
- Easy to validate
- Widely used for APIs
- Easily extensible

---

## UUID

Each attestation receives a UUID to ensure uniqueness without requiring a centralized database.

---

## Timestamp

All timestamps are recorded in UTC using ISO-8601 format.

This ensures interoperability across systems and avoids timezone ambiguity.

---

## Manual Capture

The metadata is entered manually during Sprint 1.

This simplifies validation of the data model before introducing automated capture mechanisms.

---

# Current Limitations

The current prototype has several intentional limitations.

It cannot:

- Detect AI usage automatically
- Verify metadata authenticity
- Prevent users from providing incorrect information
- Integrate with IDEs
- Intercept AI prompts
- Sign attestations
- Verify integrity

These limitations are expected and will be addressed in subsequent development phases.

---

# Deliverables

Sprint 1 delivers:

- Initial Contextual Attestation schema
- Metadata capture prototype
- JSON serialization
- Local attestation storage
- Basic CLI interface

---

# Lessons Learned

The primary outcome of Sprint 1 is the validation of the data model rather than the implementation of security mechanisms.

Before provenance can be protected, it must first be represented in a structured format.

Sprint 1 establishes this representation and provides the foundation for future work.

---

# Next Sprint

Sprint 2 will focus on automated provenance capture.

Rather than asking the user to enter metadata manually, AgentGuard will begin exploring mechanisms for automatically collecting AI interaction data through development tools such as IDE extensions, Git hooks, CLI wrappers, or AI coding agent integrations.

The objective is to reduce reliance on manual input while preserving accurate contextual information.

---

# Sprint Status

Completed.