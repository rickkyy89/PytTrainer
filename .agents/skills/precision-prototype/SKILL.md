---
name: precision-prototype
description: Build a single, highly-detailed throwaway prototype after relentlessly interviewing the user about exact dimensions, scale, position, and control functions.
---

# Precision Prototype

A precision prototype is **throwaway code that answers a specific UI/layout/interactivity design question**. Unlike general prototypes that produce multiple rapid variations, a precision prototype focuses on **exactly one UI design** built to precise user specifications gathered through an upfront grilling session.

## 1. Interview the user relentlessly (Grilling)

Before writing any code, walk through an intense, one-by-one grilling session using the `grilling` loop. Ask questions **one at a time**, waiting for feedback on each before moving to the next.

For each question, provide your recommended answer.

Walk down the decision tree resolving dependencies one-by-one:
1. **Purpose:** What exact question or hypothesis is this prototype testing?
2. **Target UI Scope:** Which specific page, section, component, or part of the page are we creating a prototype for?
3. **Target Elements:** Which specific elements need the ability to adjust scale, position, alignment, or layout dynamically?
4. **Control Mechanisms:** What exact control functions or UI mechanisms should adjust those properties (e.g., range sliders, +/- step buttons, numeric inputs, toggle buttons)?
5. **State & Constraints:** What constraints, boundaries, or live state readouts must be visible on the screen while tweaking parameters?

Do not start coding until the user explicitly confirms that a shared understanding has been reached.

## 2. Build exactly ONE precision prototype

Once aligned, create a single, clean prototype tailored to the exact specifications.

## 3. Apply validated parameters to production

After the user has interacted with the prototype and tuned the scale, position, and control settings, apply the validated values to production mode to ensure production matches prototype mode exactly:

1. **Extract & Map:** Extract final state readout values from the prototype and map each parameter directly to its corresponding production file, component prop, or CSS variable.
2. **Apply Changes:** Edit the production code and stylesheets to replace defaults/placeholders with the exact validated values.
3. **Verify Alignment:** Verify that production code compiles cleanly and matches the prototype values.

## Rules

1. **Throwaway from day one, and clearly marked as such.** Locate the prototype code close to where it will actually be used (next to the module or page it's prototyping for) so context is obvious — but name it so a casual reader can see it's a prototype, not production. For throwaway UI routes, obey whatever routing convention the project already uses; don't invent a new top-level structure.
2. **One command to run.** Whatever the project's existing task runner supports — `pnpm <name>`, `python <path>`, `bun <path>`, `npm run dev`, etc. The user must be able to start it without thinking.
3. **No persistence by default.** State lives in memory. If sliders/controls adjust scale and position, keep that transient state local.
4. **Skip the polish.** No automated tests, no complex error handling beyond making it runnable. Focus on high-fidelity interactivity for the target controls.
5. **Surface the state.** Display a dedicated floating panel or live readout showing exact scale, position, and control state values so the user can easily copy or inspect the validated parameters.
6. **Capture it when done.** Fold any validated decision into the real code, then capture the prototype itself on a throwaway branch or PR.
