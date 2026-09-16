import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MotionSessionsPanel } from "./MotionSessionsPanel";

afterEach(cleanup);

it("shows one motion with separate completion and upload progress and per-side group targets", () => {
  render(<MotionSessionsPanel records={[]} onOpen={vi.fn()} sessions={[{
    id: 1, action_name: "腿部后踢", training_date: "2026-09-16", planned_sets: 3,
    completed_sets: 2, uploaded_sets: 1, repetitions: 10, count_unit: "per_side",
    status: "partial", actual_duration_seconds: 80,
    sets: [{ index: 1, completed: true, uploaded: true, video_id: 5 }, { index: 2, completed: true, uploaded: false, video_id: null }],
  }]} />);
  expect(screen.getByText("每侧 10 个 × 3 组")).toBeInTheDocument();
  expect(screen.getByText("部分完成")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand row" }));
  expect(screen.getAllByText("2/3 组", { selector: ".ant-table-cell" })[0]).toBeInTheDocument();
  expect(screen.getByText("待上传")).toBeInTheDocument();
  expect(screen.getByText("目标为左右每侧个数，分析结果为双侧合计。")).toBeInTheDocument();
});
