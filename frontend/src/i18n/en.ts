import type { Messages } from "@/i18n/pt-PT";

// English. Typed as Messages: a missing or extra key fails the build.
export const en: Messages = {
  product: "Enterprise Knowledge AI",
  productShort: "EKA",
  signIn: {
    title: "Answers from your company, with the sources in view.",
    body: "Ask what you need to know. The answer comes from the documents you can access, with the exact passage it came from.",
    action: "Sign in",
    note: "You sign in with your organization\u2019s account.",
  },
  specimen: {
    label: "Example of an answer with its source",
    question: "How many days of holiday do I get a year?",
    answer: "You are entitled to 25 working days of holiday per calendar year",
    source: "Employee Handbook",
    section: "1. Holidays",
    quoted: (text: string) => `\u201c${text}\u201d`,
    passage: "Every employee is entitled to 25 working days of holiday per calendar year.",
  },
  nav: {
    main: "Main",
    assistant: "Assistant",
    signOut: "Sign out",
    organization: "Organization",
    switchOrganization: "Switch organization",
  },
  language: {
    label: "Interface language",
    saved: "Language changed",
  },
  assistant: {
    title: "Assistant",
    placeholder: "Type your question, for example: how many days of holiday do I get a year?",
    ask: "Ask",
    asking: "Searching and writing\u2026",
    hint: "Enter sends the question. Shift+Enter starts a new line.",
    emptyTitle: "What do you need to know?",
    emptyBody: "Answers cite the passage they come from. If the documents you can access do not answer, I tell you I don\u2019t know. I never make things up.",
    sources: "Sources",
    source: (number: number) => `Source ${number}`,
    sourcesConsulted: "Consulted, not cited",
    noAnswerTitle: "No reliable answer",
    verified: "Checked against the sources",
    elapsed: (seconds: number) => `${seconds} s`,
    errorTitle: "Could not answer",
    errors: {
      unavailable: "The answer model is not available. Check that it is running and try again.",
      forbidden: "You do not have access to this organization.",
      invalid: "The question is not valid. Write between 1 and 500 characters.",
      signedOut: "Your session has ended. Sign in again to continue.",
      network: "Could not reach the server. Check your connection and try again.",
      unknown: "Something went wrong on our side. Try again in a moment.",
    },
    tryAgain: "Try again",
  },
  noOrganization: {
    title: "You are not in an organization yet",
    body: "Ask an administrator at your company to invite you. Once you accept the invitation, the assistant is available here.",
  },
};
