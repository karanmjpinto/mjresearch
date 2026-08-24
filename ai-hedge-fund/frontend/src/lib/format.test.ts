import { describe, expect, it } from "vitest";
import { formatValue, formatNumber } from "./format";

/**
 * These functions decide how every computed figure is finally read. A rounding
 * or abbreviation bug here is indistinguishable to a user from a wrong number
 * upstream — the harness can verify a value and this layer can still print it
 * as something else.
 */
describe("formatValue", () => {
  it("renders absent values as a dash rather than as zero", () => {
    // The distinction that matters: 'not computed' must never read as 0.
    expect(formatValue(null)).toBe("—");
    expect(formatValue(undefined)).toBe("—");
  });

  it("treats non-finite numbers as absent, not as text", () => {
    // NaN slipping through as "NaN" reads like a value; Infinity worse still.
    expect(formatValue(NaN)).toBe("—");
    expect(formatValue(Infinity)).toBe("—");
    expect(formatValue(-Infinity)).toBe("—");
  });

  it("spells booleans out", () => {
    expect(formatValue(true)).toBe("yes");
    expect(formatValue(false)).toBe("no");
  });

  it("abbreviates at billions and millions", () => {
    expect(formatValue(6_920_000_000)).toBe("6.92B");
    expect(formatValue(1_500_000)).toBe("1.50M");
  });

  it("abbreviates negatives by magnitude, keeping the sign", () => {
    expect(formatValue(-2_500_000_000)).toBe("-2.50B");
    expect(formatValue(-3_250_000)).toBe("-3.25M");
  });

  it("switches to abbreviation exactly at the threshold", () => {
    expect(formatValue(999_999)).toBe("999999");
    expect(formatValue(1_000_000)).toBe("1.00M");
    expect(formatValue(999_999_999)).toBe("1000.00M");
    expect(formatValue(1_000_000_000)).toBe("1.00B");
  });

  it("leaves integers bare and rounds fractions to two places", () => {
    expect(formatValue(42)).toBe("42");
    expect(formatValue(0)).toBe("0");
    expect(formatValue(3.14159)).toBe("3.14");
    expect(formatValue(2.005)).toBe("2.00");
  });

  it("passes strings through unchanged", () => {
    expect(formatValue("uptrend")).toBe("uptrend");
    expect(formatValue("")).toBe("");
  });
});

describe("formatNumber", () => {
  it("appends the unit", () => {
    expect(formatNumber(48.28, { unit: "%" })).toBe("48.28%");
    expect(formatNumber(12, { unit: "×" })).toBe("12×");
  });

  it("shows a leading plus only when the sign is the point", () => {
    expect(formatNumber(48.28, { unit: "%", signed: true })).toBe("+48.28%");
    expect(formatNumber(-48.28, { unit: "%", signed: true })).toBe("-48.28%");
    expect(formatNumber(48.28, { unit: "%" })).toBe("48.28%");
  });

  it("does not sign a zero", () => {
    // '+0%' claims a direction the number does not have.
    expect(formatNumber(0, { unit: "%", signed: true })).toBe("0%");
  });

  it("works with no options at all", () => {
    expect(formatNumber(7)).toBe("7");
  });
});
