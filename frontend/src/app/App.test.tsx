import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the admin navigation", () => {
    render(<App />);
    expect(screen.getByText("患者档案")).toBeInTheDocument();
    expect(screen.getByText("研究项目")).toBeInTheDocument();
    expect(screen.getByText("CRF 报告")).toBeInTheDocument();
  });
});

