import { extractDocIdFromGoogleDocUrl } from '../lib/googleDocs';

test('extracts ID from full Google Docs URL', () => {
  const input = 'https://docs.google.com/document/d/abc123456789012345678901234567890123456789/edit';
  expect(extractDocIdFromGoogleDocUrl(input)).toBe('abc123456789012345678901234567890123456789');
});

test('passes through already sanitized IDs and other strings', () => {
  const rawId = 'abc123456789012345678901234567890123456789';
  expect(extractDocIdFromGoogleDocUrl(rawId)).toBe(rawId);
  expect(extractDocIdFromGoogleDocUrl('notes')).toBe('notes');
});
