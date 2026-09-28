import { describe, expect, it } from "vitest";
import { applicantNameOf } from "./fields";

// The frozen contract leaves applicantFields a bare object, so which key holds the name is a
// guess — CR-5 records both tracks guessing differently. These pin that every shape seen in
// the wild resolves, and that the queue and the report can never disagree about who applied.
describe("applicantNameOf", () => {
  it("reads the key the real API sends", () => {
    expect(applicantNameOf({ fullName: "Yogesh Mandvi" })).toBe("Yogesh Mandvi");
  });

  it("reads the key the mock fixtures send", () => {
    expect(applicantNameOf({ applicantName: "Asha Rai" })).toBe("Asha Rai");
  });

  it("takes the first match when an application carries both", () => {
    expect(applicantNameOf({ fullName: "Real One", applicantName: "Mock One" })).toBe("Real One");
  });

  it("returns null instead of a blank, a space, or a non-string", () => {
    expect(applicantNameOf({})).toBeNull();
    expect(applicantNameOf({ fullName: "   " })).toBeNull();
    expect(applicantNameOf({ fullName: 42 })).toBeNull();
  });
});
