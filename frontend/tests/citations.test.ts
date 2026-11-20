import { excerpt, paragraphs, passageText, splitAnswer } from "@/lib/citations";

describe("splitAnswer", () => {
  it("cuts text and citations in order", () => {
    expect(splitAnswer("Tens 25 dias [1]. Marca no portal [2][3].")).toEqual([
      { kind: "text", text: "Tens 25 dias" },
      { kind: "citation", number: 1 },
      { kind: "text", text: ". Marca no portal" },
      { kind: "citation", number: 2 },
      { kind: "citation", number: 3 },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves text without citations whole", () => {
    expect(splitAnswer("Sem fontes.")).toEqual([{ kind: "text", text: "Sem fontes." }]);
  });

  it("does not read numbers in brackets of three digits as citations", () => {
    expect(splitAnswer("Artigo [123]")).toEqual([{ kind: "text", text: "Artigo [123]" }]);
  });
});

describe("paragraphs", () => {
  it("splits at blank lines only", () => {
    expect(paragraphs("Um.\nDois.\n\n  Tres.  ")).toEqual(["Um.\nDois.", "Tres."]);
  });
});

describe("passageText", () => {
  it("does not repeat the section heading the margin already shows", () => {
    expect(passageText("1. F\u00e9rias Cada colaborador tem 25 dias.", "1. F\u00e9rias")).toBe("Cada colaborador tem 25 dias.");
    expect(passageText("Cada colaborador tem 25 dias.", "1. F\u00e9rias")).toBe("Cada colaborador tem 25 dias.");
    expect(passageText("Texto.", null)).toBe("Texto.");
  });
});

describe("excerpt", () => {
  it("keeps the first words", () => {
    expect(excerpt("um dois tres quatro", 2)).toBe("um dois\u2026");
    expect(excerpt("curto", 2)).toBe("curto");
  });
});
