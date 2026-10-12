# Design System

## Direction

Enterprise construction-safety product: clear, trustworthy, information-dense and accessible.

## Rules

- Keep AI-generated content visually distinct.
- Critical/high risk needs text labels, not color only.
- Use consistent spacing and component patterns.
- Define loading, empty, error and partial states.
- Use semantic HTML and keyboard navigation.

## Screens

Dashboard; Incident List; Incident Workspace; Evidence Viewer; Investigation; RCA/Compliance; CAPA; Workflow; Knowledge; Analytics; Administration.

## Implemented (0.2.0)

- Tokens in `frontend/app/globals.css` (light and dark, selected per mode); system sans; charts use one hue with
  values at the bar tip, hover tooltips and a table view.
- AI-generated content sits in panels with a violet left rule and an "AI-generated" label; AI-proposed actions keep
  the rule until reviewed.
- Severity and risk use the fixed status palette with an icon and a text label, never colour alone.
- Loading, empty, error (with correlation ID) and partial states (failed agents) are shown; skip link, labelled
  form controls and keyboard-focusable chart rows.
- Screens: login, dashboard, incident list, report incident, incident workspace (investigation, review, work,
  verification, closure, evidence, lifecycle, report download), action queue, knowledge search, audit.
