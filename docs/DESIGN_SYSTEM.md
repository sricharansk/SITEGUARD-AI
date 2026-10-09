# Design System

Source: Blueprint Part 5. No web app exists yet; these rules apply from Prompt 02 onwards.

## Direction

Enterprise construction-safety product: clear hierarchy, trustworthy, dense but readable data views, accessible.

- High visibility for risk and overdue work.
- AI-generated content is visually separated from verified evidence and human decisions, and is labelled as AI
  decision support.
- Critical/high risk carries a text label, not color alone.
- Consistent spacing and component patterns.

## State rules

Every important screen defines: loading, empty, error, partial-result, success and unauthorized states. Errors show
the API's message and correlation ID so support can trace them.

## Primary screens

Dashboard; incident list/filter; incident command center; evidence viewer; investigation workspace;
RCA/compliance workspace; CAPA board; workflow timeline; knowledge/documents; analytics; administration.

## Accessibility

Semantic HTML; keyboard navigation; visible focus states; accessible labels; text + icon + status semantics; never
rely on color alone.
