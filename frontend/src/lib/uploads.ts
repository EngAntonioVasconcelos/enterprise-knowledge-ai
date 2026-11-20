// What the upload screen and its route share: the limits the backend
// applies, checked here first so the person learns at once.
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"] as const;
export const UPLOAD_PROVIDER = "file_upload";

export type UploadErrorKind =
  | "tooLarge"
  | "unsupported"
  | "empty"
  | "forbidden"
  | "signedOut"
  | "unavailable";

export function checkFile(file: { name: string; size: number }): UploadErrorKind | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) return "unsupported";
  if (file.size === 0) return "empty";
  if (file.size > MAX_UPLOAD_BYTES) return "tooLarge";
  return null;
}

export function uploadErrorFromStatus(status: number): UploadErrorKind {
  if (status === 401) return "signedOut";
  if (status === 403) return "forbidden";
  if (status === 413) return "tooLarge";
  if (status === 415) return "unsupported";
  return "unavailable";
}

/** The kind of a document, in words a person uses. */
export function documentKind(mimeType: string | null): "pdf" | "word" | "text" | "other" {
  if (mimeType === "application/pdf") return "pdf";
  if (mimeType?.includes("wordprocessingml")) return "word";
  if (mimeType?.startsWith("text/")) return "text";
  return "other";
}
