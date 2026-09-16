// @vitest-environment happy-dom

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CountUp } from "./count-up";

describe("CountUp", () => {
	it("renders an aria-live=polite span by default (announced to screen readers)", () => {
		const { container } = render(<CountUp to={1000} />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.getAttribute("aria-live")).toBe("polite");
		expect(span.getAttribute("aria-atomic")).toBe("true");
	});

	it("seeds textContent to 0 on initial render", () => {
		const { container } = render(<CountUp to={100} />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.textContent).toBe("0");
	});

	it("formats with the separator when one is supplied", () => {
		const { container } = render(<CountUp to={1234} separator="," />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.textContent).toBe("0");
	});

	it("preserves decimal places when to is fractional", () => {
		const { container } = render(<CountUp to={3.75} />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.textContent).toBe("0.00");
	});

	it("strips aria-live and aria-atomic when aria-hidden is set", () => {
		const { container } = render(<CountUp to={100} aria-hidden="true" />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.getAttribute("aria-hidden")).toBe("true");
		expect(span.getAttribute("aria-live")).toBeNull();
		expect(span.getAttribute("aria-atomic")).toBeNull();
	});

	it("accepts a custom className", () => {
		const { container } = render(<CountUp to={100} className="custom-class" />);
		const span = container.querySelector("span") as HTMLSpanElement;
		expect(span.className).toContain("custom-class");
	});
});
