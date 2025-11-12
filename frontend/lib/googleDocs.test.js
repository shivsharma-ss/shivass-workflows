import { describe, expect, it } from 'vitest';

import { extractDocIdFromGoogleDocUrl } from './googleDocs';

describe('extractDocIdFromGoogleDocUrl', () => {
  it('returns the ID from a standard edit link', () => {
    const url = 'https://docs.google.com/document/d/abc123DEF456/edit';
    expect(extractDocIdFromGoogleDocUrl(url)).toBe('abc123DEF456');
  });

  it('handles links that include a user segment', () => {
    const url = 'https://docs.google.com/document/u/0/d/long-doc-id-789/view';
    expect(extractDocIdFromGoogleDocUrl(url)).toBe('long-doc-id-789');
  });

  it('preserves a plain document ID', () => {
    const docId = 'plainDocId_1234567890';
    expect(extractDocIdFromGoogleDocUrl(docId)).toBe(docId);
  });

  it('returns trimmed input when no ID can be extracted', () => {
    const input = '   not-a-doc-link   ';
    expect(extractDocIdFromGoogleDocUrl(input)).toBe('not-a-doc-link');
  });
});
