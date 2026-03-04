---
name: react
description: Build and refactor production-quality React applications and components using TypeScript, reusable patterns, and clean state/data flow. Use for React UI features, component architecture, hooks, performance tuning, forms, and frontend bug fixing.
license: Complete terms in LICENSE.txt
---

This skill is for implementing and improving React codebases with pragmatic, maintainable architecture.

Use this skill when the user asks to:
- Create React pages/components/hooks
- Refactor large React components into reusable units
- Fix React UI/behavior bugs and state issues
- Improve performance (memoization, render splitting, list optimization)
- Integrate API calls, loading/error states, and optimistic UX
- Implement accessibility-safe interactive UI in React

## Working Style

1. Start with the existing app conventions (file structure, naming, styling system, routing).
2. Prefer TypeScript-first React with explicit prop typing.
3. Keep components focused and composable; extract logic into hooks when reused.
4. Handle async data explicitly with loading, empty, error, and success states.
5. Preserve UI behavior while making minimal, surgical changes in existing codebases.

## Component Patterns

- Prefer controlled components for forms with explicit validation states.
- Keep presentational concerns in components and business logic in hooks/helpers.
- Use `useMemo` and `useCallback` only where they measurably reduce re-renders.
- Avoid prop drilling when local composition or context is clearer.
- Keep side effects in `useEffect` deterministic with complete dependency arrays.

## UX & Accessibility Baseline

- Every interactive control must be keyboard accessible.
- Use semantic elements before custom roles.
- Provide labels, helper text, and actionable error messages.
- Ensure focus states are visible and color contrast is sufficient.

## API/Data Integration

- Normalize API responses before rendering.
- Treat server data as nullable/partial and guard rendering paths.
- Surface recoverable errors in UI; avoid silent failures.
- Keep network request logic centralized (API client/service modules).

## Quality Checks

Before finishing:
- Run TypeScript build/lint/tests where available.
- Confirm no regressions in nearby views.
- Keep diffs tight and aligned with project style.
