import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { TrainingVideoWearablePanel } from "./TrainingVideoWearablePanel";
import type { TrainingVideoWearableWindowResponse } from "./types";

vi.mock("@ant-design/charts", () => ({
  Line: ({
    data,
  }: {
    data: Array<{ series: string; value: number }>;
  }) => (
    <div aria-label="训练时段趋势图">
      {data.map((point) => `${point.series}:${point.value}`).join("|")}
    </div>
  ),
}));

const getComputedStyle = window.getComputedStyle;

beforeAll(() => {
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
});

afterEach(cleanup);

afterAll(() => {
  vi.restoreAllMocks();
});

const responseWithoutOxygen: TrainingVideoWearableWindowResponse = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 89.5, maximum: 112, minimum: 67, count: 4 },
    },
    blood_pressure: {
      points: [
        {
          measured_at: "2026-08-06T01:34:00Z",
          systolic: 126,
          diastolic: 78,
        },
      ],
      statistics: {
        systolic: { average: 126.3, maximum: 132, minimum: 121 },
        diastolic: { average: 78, maximum: 82, minimum: 74 },
        count: 3,
      },
    },
  },
};

const oxygenOnlyResponse: TrainingVideoWearableWindowResponse = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    blood_oxygen: {
      points: [{ measured_at: "2026-08-06T01:35:00Z", value: 97 }],
    },
  },
};

describe("TrainingVideoWearablePanel", () => {
  it("renders only available metric tabs and heart/blood-pressure statistics", () => {
    render(<TrainingVideoWearablePanel data={responseWithoutOxygen} />);

    expect(screen.getByRole("tab", { name: "心率" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "血压" })).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "血氧" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("89.5")).toBeInTheDocument();
    expect(screen.getByText("收缩压（mmHg）")).toBeInTheDocument();
    expect(screen.getByText("舒张压（mmHg）")).toBeInTheDocument();
  });

  it("keeps statistic rows ordered and reuses the blood-pressure count", () => {
    render(<TrainingVideoWearablePanel data={responseWithoutOxygen} />);

    const rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByText("心率（次/分）")).toBeInTheDocument();
    expect(within(rows[1]).getByText("4")).toBeInTheDocument();
    expect(
      within(rows[2]).getByText("收缩压（mmHg）"),
    ).toBeInTheDocument();
    expect(within(rows[2]).getByText("3")).toBeInTheDocument();
    expect(
      within(rows[3]).getByText("舒张压（mmHg）"),
    ).toBeInTheDocument();
    expect(within(rows[3]).getByText("3")).toBeInTheDocument();
  });

  it("renders oxygen trend without a statistics table", () => {
    render(<TrainingVideoWearablePanel data={oxygenOnlyResponse} />);

    expect(screen.getByRole("tab", { name: "血氧" })).toBeInTheDocument();
    expect(screen.queryByText("训练时段统计")).not.toBeInTheDocument();
  });

  it("switches the rendered chart data with the selected metric tab", () => {
    render(<TrainingVideoWearablePanel data={responseWithoutOxygen} />);

    expect(
      within(screen.getByRole("tabpanel")).getByLabelText("训练时段趋势图"),
    ).toHaveTextContent("心率:86");

    fireEvent.click(screen.getByRole("tab", { name: "血压" }));

    expect(screen.getByRole("tab", { name: "血压" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      within(screen.getByRole("tabpanel")).getByLabelText("训练时段趋势图"),
    ).toHaveTextContent("收缩压:126|舒张压:78");
  });

  it("renders nothing when the response is unavailable", () => {
    const { container } = render(
      <TrainingVideoWearablePanel data={{ available: false }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the available response has no metrics", () => {
    const { container } = render(
      <TrainingVideoWearablePanel
        data={{
          available: true,
          training_started_at: "2026-08-06T01:32:14Z",
          training_ended_at: "2026-08-06T01:41:27Z",
          metrics: {},
        }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when every metric key has no points", () => {
    const { container } = render(
      <TrainingVideoWearablePanel
        data={{
          available: true,
          training_started_at: "2026-08-06T01:32:14Z",
          training_ended_at: "2026-08-06T01:41:27Z",
          metrics: {
            heart_rate: {
              points: [],
              statistics: {
                average: 89.5,
                maximum: 112,
                minimum: 67,
                count: 4,
              },
            },
            blood_pressure: {
              points: [],
              statistics: {
                systolic: { average: 126.3, maximum: 132, minimum: 121 },
                diastolic: { average: 78, maximum: 82, minimum: 74 },
                count: 3,
              },
            },
            blood_oxygen: { points: [] },
          },
        }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("hides an empty metric tab and its statistics when another metric has points", () => {
    render(
      <TrainingVideoWearablePanel
        data={{
          ...responseWithoutOxygen,
          metrics: {
            ...responseWithoutOxygen.metrics,
            heart_rate: {
              points: [],
              statistics: {
                average: 89.5,
                maximum: 112,
                minimum: 67,
                count: 4,
              },
            },
          },
        }}
      />,
    );

    expect(
      screen.queryByRole("tab", { name: "心率" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "血压" })).toBeInTheDocument();
    expect(screen.queryByText("心率（次/分）")).not.toBeInTheDocument();
    expect(screen.getByText("收缩压（mmHg）")).toBeInTheDocument();
  });
});
