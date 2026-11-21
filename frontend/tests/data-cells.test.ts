import { cellText, isNumberCell, numberColumns } from "@/lib/data-cells";

describe("database values", () => {
  it("are written as in the language", () => {
    expect(cellText("19209.94", "pt-PT").replace(/\s/g, " ")).toBe("19 209,94");
    expect(cellText("19209.94", "en")).toBe("19,209.94");
    expect(cellText(55, "pt-PT")).toBe("55");
    expect(cellText("20.00", "pt-PT")).toBe("20,00");
  });

  it("keep codes and text as they came", () => {
    expect(cellText("018", "pt-PT")).toBe("018");
    expect(cellText("Cliente 018", "pt-PT")).toBe("Cliente 018");
    expect(isNumberCell("2026-11-01")).toBe(false);
  });

  it("align number columns to the right", () => {
    expect(numberColumns([["Lisboa", "33488.20"], ["Norte", null]], 2)).toEqual([false, true]);
  });
});
