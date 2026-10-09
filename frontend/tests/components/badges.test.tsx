// Risk and severity are text badges with a distinct shape per level, so meaning never depends on colour alone.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskBadge, SeverityBadge, StatusBadge, WorkBadge } from "@/components/badges";

describe("RiskBadge", () => {
  it.each([
    ["LOW", "circle"],
    ["MEDIUM", "diamond"],
    ["HIGH", "triangle"],
    ["CRITICAL", "octagon"],
  ])("%s shows its band as text with a %s icon", (band, shape) => {
    const { container } = render(<RiskBadge band={band} score={12} />);
    const wrapper = container.querySelector(`[data-level="${band}"]`);
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveAttribute("data-shape", shape);
    expect(wrapper?.querySelector("svg")).not.toBeNull();
    expect(screen.getByText(`${band} · 12`)).toBeVisible();
  });

  it("names what the badge is for screen readers and as a tooltip", () => {
    const { container } = render(<RiskBadge band="HIGH" score={16} />);
    expect(container).toHaveTextContent("Risk (band and score): HIGH · 16");
    expect(container.querySelector("[title]")).toHaveAttribute("title", "Risk (band and score)");
  });

  it("gives every level a different shape", () => {
    const shapes = ["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((band) => {
      const { container, unmount } = render(<RiskBadge band={band} />);
      const shape = container.querySelector("[data-shape]")?.getAttribute("data-shape");
      unmount();
      return shape;
    });
    expect(new Set(shapes).size).toBe(4);
  });

  it("falls back to a neutral dash for an unknown band and still prints it", () => {
    const { container } = render(<RiskBadge band="UNKNOWN" />);
    expect(container.querySelector("[data-shape]")).toHaveAttribute("data-shape", "dash");
    expect(screen.getByText("UNKNOWN")).toBeVisible();
  });
});

describe("other badges", () => {
  it("SeverityBadge prints the level with the same shape scale", () => {
    const { container } = render(<SeverityBadge severity="CRITICAL" />);
    expect(container.querySelector("[data-shape]")).toHaveAttribute("data-shape", "octagon");
    expect(container).toHaveTextContent("Severity: CRITICAL");
  });

  it("StatusBadge humanizes the status", () => {
    render(<StatusBadge status="PENDING_APPROVAL" />);
    expect(screen.getByText("Pending approval")).toBeVisible();
  });

  it("WorkBadge says a completed action still awaits verification", () => {
    render(<WorkBadge status="COMPLETED" />);
    expect(screen.getByText("Completed, awaiting verification")).toBeVisible();
  });
});
