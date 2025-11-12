// Extract the canonical Docs ID from either a full URL or a pasted ID.
export function extractDocIdFromGoogleDocUrl(input) {
  if (!input) {
    return input;
  }

  const trimmed = input.trim();
  const docPattern = /\/document\/(?:u\/\d+\/)?d\/([a-zA-Z0-9_-]+)/;
  const match = trimmed.match(docPattern);
  if (match) {
    return match[1];
  }

  // Google Docs IDs are typically 39+ characters; require that minimum when users paste raw IDs.
  const docIdPattern = /^[a-zA-Z0-9_-]{39,}$/;
  if (docIdPattern.test(trimmed)) {
    return trimmed;
  }

  return trimmed;
}
