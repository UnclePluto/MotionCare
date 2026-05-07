import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the admin navigation", () => {
    render(<App />);
    expect(screen.getAllByText("患者档案").length).toBeGreaterThan(0);
    expect(screen.getAllByText("研究项目").length).toBeGreaterThan(0);
    expect(screen.getAllByText("CRF 报告").length).toBeGreaterThan(0);
  });
});

