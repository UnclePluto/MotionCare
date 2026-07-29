# Wechat Miniapp Full Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the whole WeChat patient miniapp around a distinct mobile-first rehabilitation style and add visible game subpackage loading progress before entering games.

**Architecture:** Keep page routes, data fetching, game rules, and upload behavior unchanged. Add a focused game subpackage loader helper with tests, then update page markup only where needed for loading state and better visual hierarchy, with the full design system implemented in `miniapp/src/app.scss`.

**Tech Stack:** Taro 4, React 18, TypeScript, Sass, Vitest, WeChat `wx.loadSubpackage`.

---

## File Structure

- Create `miniapp/src/pages/prescription/gameSubpackage.ts`: isolated wrapper for game subpackage name, game URL construction, progress normalization, and runtime loading.
- Create `miniapp/src/pages/prescription/gameSubpackage.test.ts`: unit tests for loader success, failure, fallback, and URL.
- Modify `miniapp/src/pages/prescription/index.tsx`: show loading progress while loading the game subpackage before navigation.
- Modify `miniapp/src/pages/home/index.tsx`, `bind/index.tsx`, `daily-health/index.tsx`, `training/index.tsx`, `action-history/index.tsx`: add light structural class names for the redesigned mobile layout without changing data flow.
- Modify `miniapp/src/pages/game-session/index.tsx`: add stable class hooks for the game stage, status bar, setup, intro, and result layouts.
- Modify `miniapp/src/app.scss`: replace generic Ant Design-like styles with the new miniapp design system and unified game styles.
- Verify `miniapp/src/app.config.ts` and `miniapp/config/index.ts`: keep game page and game assets in `pages/game-session` subpackage.

## Tasks

### Task 1: Game Subpackage Loader

- [x] Add failing tests in `miniapp/src/pages/prescription/gameSubpackage.test.ts` for `gameSessionUrl`, progress updates, fallback when `loadSubpackage` is unavailable, and rejection on failure.
- [x] Run `cd miniapp && npm run test -- src/pages/prescription/gameSubpackage.test.ts` and confirm it fails because the helper does not exist.
- [x] Implement `miniapp/src/pages/prescription/gameSubpackage.ts`.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Prescription Page Loading Flow

- [x] Modify `miniapp/src/pages/prescription/index.tsx` so game actions call `loadGameSessionSubpackage` before `Taro.navigateTo`.
- [x] Add state for loading action id, progress, and error.
- [x] Render a visible progress bar while the game subpackage is loading.
- [x] Keep non-game actions navigating directly to the manual training page.

### Task 3: Whole Miniapp Markup Hooks

- [x] Add page-specific hero, status-grid, form-stack, and list class hooks to home, bind, prescription, training, daily health, and action history pages.
- [x] Keep all API calls, input values, submit behavior, retry upload behavior, and navigation unchanged.
- [x] Add game page class hooks for setup, playing, intro, result, stage, and controls.

### Task 4: Full Visual System

- [x] Replace generic `miniapp/src/app.scss` styles with the new design system tokens and component rules.
- [x] Style buttons, cards, inputs, alerts, progress bars, binding code slots, stats, lists, and game controls.
- [x] Ensure all click targets are at least 72px compact or 88px primary height.
- [x] Ensure game tiles, cards, puzzle tiles, and feedback bars remain stable and non-overlapping.

### Task 5: Verification

- [x] Run `cd miniapp && npm run test`.
- [x] Run `cd miniapp && npm run build:weapp`.
- [x] Inspect `miniapp/dist/app.json` and package asset locations to confirm the game page remains in `subPackages`.
- [x] Check built package sizes and confirm game assets remain under `dist/pages/game-session/assets`.

Git commits are not part of this plan unless the user explicitly requests them.
