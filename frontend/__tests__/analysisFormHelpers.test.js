import { describe, expect, it, beforeAll, afterAll } from 'vitest';

import {
  buildInitialForm,
  clampBoost,
  cloneDefaultChannels,
  computeChipAccent,
  formatBoost,
  generateChannelId,
} from '../components/analysisFormHelpers';

let originalRandomUUID;

beforeAll(() => {
  // Mock crypto.randomUUID for deterministic tests
  originalRandomUUID = globalThis.crypto?.randomUUID;
  let counter = 0;
  const mockUUID = () => `test-uuid-${counter += 1}`;
  if (!globalThis.crypto) {
    Object.defineProperty(globalThis, 'crypto', {
      value: { randomUUID: mockUUID },
      writable: true,
    });
  } else {
    globalThis.crypto.randomUUID = mockUUID;
  }
});

afterAll(() => {
  if (originalRandomUUID && globalThis.crypto) {
    globalThis.crypto.randomUUID = originalRandomUUID;
  }
});

describe('clampBoost', () => {
  it('should clamp values within 0.5 to 2.0 range', () => {
    expect(clampBoost(1.5)).toBe(1.5);
    expect(clampBoost(0.8)).toBe(0.8);
    expect(clampBoost(1.9)).toBe(1.9);
  });

  it('should clamp values below 0.5 to 0.5', () => {
    expect(clampBoost(0.3)).toBe(0.5);
    expect(clampBoost(0)).toBe(0.5);
    expect(clampBoost(-1)).toBe(0.5);
  });

  it('should clamp values above 2.0 to 2.0', () => {
    expect(clampBoost(2.5)).toBe(2);
    expect(clampBoost(10)).toBe(2);
    expect(clampBoost(100)).toBe(2);
  });

  it('should return 1.1 for NaN values', () => {
    expect(clampBoost('invalid')).toBe(1.1);
    expect(clampBoost(NaN)).toBe(1.1);
    expect(clampBoost(undefined)).toBe(1.1);
  });

  it('should handle string numbers', () => {
    expect(clampBoost('1.5')).toBe(1.5);
    expect(clampBoost('0.7')).toBe(0.7);
  });

  it('should handle edge case values', () => {
    expect(clampBoost(0.5)).toBe(0.5);
    expect(clampBoost(2.0)).toBe(2.0);
  });
});

describe('formatBoost', () => {
  it('should format boost values with × symbol', () => {
    expect(formatBoost(1.5)).toBe('1.5×');
    expect(formatBoost(0.8)).toBe('0.8×');
    expect(formatBoost(1.25)).toBe('1.25×');
  });

  it('should remove trailing .00 from whole numbers', () => {
    expect(formatBoost(1)).toBe('1×');
    expect(formatBoost(2)).toBe('2×');
  });

  it('should clamp values before formatting', () => {
    expect(formatBoost(5)).toBe('2×');
    expect(formatBoost(0.1)).toBe('0.5×');
  });

  it('should handle NaN values', () => {
    expect(formatBoost('invalid')).toBe('1.1×');
  });

  it('should format to 2 decimal places', () => {
    expect(formatBoost(1.555)).toBe('1.56×');
    expect(formatBoost(1.234)).toBe('1.23×');
  });
});

describe('generateChannelId', () => {
  it('should generate unique IDs using crypto.randomUUID', () => {
    const id1 = generateChannelId();
    const id2 = generateChannelId();

    expect(id1).toMatch(/^test-uuid-\d+$/);
    expect(id2).toMatch(/^test-uuid-\d+$/);
    expect(id1).not.toBe(id2);
  });

  it('should fallback when crypto.randomUUID is unavailable', () => {
    const originalCrypto = globalThis.crypto;
    delete globalThis.crypto;

    const id = generateChannelId();
    expect(id).toMatch(/^channel-\d+-[0-9a-f]+$/);

    globalThis.crypto = originalCrypto;
  });

  it('should generate different IDs on subsequent calls', () => {
    const ids = new Set();
    for (let i = 0; i < 10; i += 1) {
      ids.add(generateChannelId());
    }
    expect(ids.size).toBe(10);
  });
});

describe('cloneDefaultChannels', () => {
  it('should return array of channel objects', () => {
    const channels = cloneDefaultChannels();

    expect(Array.isArray(channels)).toBe(true);
    expect(channels.length).toBeGreaterThan(0);
  });

  it('should include required properties', () => {
    const channels = cloneDefaultChannels();

    channels.forEach((channel) => {
      expect(channel).toHaveProperty('id');
      expect(channel).toHaveProperty('name');
      expect(channel).toHaveProperty('boost');
      expect(channel).toHaveProperty('isDefault');
    });
  });

  it('should generate unique IDs for each channel', () => {
    const channels = cloneDefaultChannels();
    const ids = channels.map((ch) => ch.id);
    const uniqueIds = new Set(ids);

    expect(uniqueIds.size).toBe(channels.length);
  });

  it('should clamp boost values', () => {
    const channels = cloneDefaultChannels();

    channels.forEach((channel) => {
      expect(channel.boost).toBeGreaterThanOrEqual(0.5);
      expect(channel.boost).toBeLessThanOrEqual(2);
    });
  });

  it('should mark channels as default', () => {
    const channels = cloneDefaultChannels();

    channels.forEach((channel) => {
      expect(typeof channel.isDefault).toBe('boolean');
    });
  });

  it('should handle missing boost property', () => {
    const channels = cloneDefaultChannels();

    // All channels should have a valid boost value
    channels.forEach((channel) => {
      expect(typeof channel.boost).toBe('number');
      expect(channel.boost).toBeGreaterThan(0);
    });
  });

  it('should create independent clones', () => {
    const channels1 = cloneDefaultChannels();
    const channels2 = cloneDefaultChannels();

    expect(channels1).not.toBe(channels2);
    expect(channels1[0]).not.toBe(channels2[0]);
  });
});

describe('computeChipAccent', () => {
  it('should generate consistent styles for same name', () => {
    const style1 = computeChipAccent('freeCodeCamp.org');
    const style2 = computeChipAccent('freeCodeCamp.org');

    expect(style1).toEqual(style2);
  });

  it('should generate different styles for different names', () => {
    const style1 = computeChipAccent('freeCodeCamp.org');
    const style2 = computeChipAccent('Tech With Tim');

    expect(style1).not.toEqual(style2);
  });

  it('should return chipStyle and avatarStyle objects', () => {
    const result = computeChipAccent('TestChannel');

    expect(result).toHaveProperty('chipStyle');
    expect(result).toHaveProperty('avatarStyle');
    expect(result.chipStyle).toHaveProperty('background');
    expect(result.chipStyle).toHaveProperty('borderColor');
    expect(result.avatarStyle).toHaveProperty('background');
    expect(result.avatarStyle).toHaveProperty('color');
  });

  it('should generate HSL gradient backgrounds', () => {
    const result = computeChipAccent('TestChannel');

    expect(result.chipStyle.background).toMatch(/linear-gradient.*hsla\(/);
    expect(result.chipStyle.borderColor).toMatch(/hsla\(/);
    expect(result.avatarStyle.background).toMatch(/linear-gradient.*hsl\(/);
  });

  it('should handle empty or null names gracefully', () => {
    const result1 = computeChipAccent('');
    const result2 = computeChipAccent(null);

    expect(result1.chipStyle).toBeDefined();
    expect(result2.chipStyle).toBeDefined();
  });

  it('should handle numeric names', () => {
    const result = computeChipAccent(12345);

    expect(result.chipStyle).toBeDefined();
    expect(result.avatarStyle).toBeDefined();
  });

  it('should generate hue values within 0-360 range', () => {
    const names = ['A', 'B', 'Channel123', 'freeCodeCamp.org', 'Tech With Tim'];

    names.forEach((name) => {
      const result = computeChipAccent(name);
      // Extract hue values from the gradient strings
      const chipBg = result.chipStyle.background;
      const hueMatches = chipBg.match(/hsla?\((\d+),/g);

      hueMatches.forEach((match) => {
        const hue = parseInt(match.match(/\d+/)[0], 10);
        expect(hue).toBeGreaterThanOrEqual(0);
        expect(hue).toBeLessThan(360);
      });
    });
  });

  it('should have consistent color for avatar style', () => {
    const result = computeChipAccent('TestChannel');

    expect(result.avatarStyle.color).toBe('#fff');
  });

  it('should generate offset hue for visual variety', () => {
    const result = computeChipAccent('TestChannel');
    const chipBg = result.chipStyle.background;

    // Should contain two different hue values
    const hues = chipBg.match(/hsla?\((\d+),/g).map((m) => parseInt(m.match(/\d+/)[0], 10));
    expect(hues[0]).not.toBe(hues[1]);
  });
});

describe('buildInitialForm', () => {
  it('should return form object with all required fields', () => {
    const form = buildInitialForm();

    expect(form).toHaveProperty('email');
    expect(form).toHaveProperty('cvDocId');
    expect(form).toHaveProperty('jobDescription');
    expect(form).toHaveProperty('jobDescriptionUrl');
    expect(form).toHaveProperty('preferredYoutubeChannels');
  });

  it('should initialize string fields as empty', () => {
    const form = buildInitialForm();

    expect(form.email).toBe('');
    expect(form.cvDocId).toBe('');
    expect(form.jobDescription).toBe('');
    expect(form.jobDescriptionUrl).toBe('');
  });

  it('should initialize preferredYoutubeChannels with default channels', () => {
    const form = buildInitialForm();

    expect(Array.isArray(form.preferredYoutubeChannels)).toBe(true);
    expect(form.preferredYoutubeChannels.length).toBeGreaterThan(0);
  });

  it('should clone default channels for independence', () => {
    const form1 = buildInitialForm();
    const form2 = buildInitialForm();

    expect(form1.preferredYoutubeChannels).not.toBe(form2.preferredYoutubeChannels);
    expect(form1.preferredYoutubeChannels[0]).not.toBe(form2.preferredYoutubeChannels[0]);
  });

  it('should have valid channel structure in preferredYoutubeChannels', () => {
    const form = buildInitialForm();

    form.preferredYoutubeChannels.forEach((channel) => {
      expect(channel).toHaveProperty('id');
      expect(channel).toHaveProperty('name');
      expect(channel).toHaveProperty('boost');
      expect(channel).toHaveProperty('isDefault');
      expect(typeof channel.id).toBe('string');
      expect(typeof channel.name).toBe('string');
      expect(typeof channel.boost).toBe('number');
      expect(typeof channel.isDefault).toBe('boolean');
    });
  });

  it('should return fresh instance each time', () => {
    const form1 = buildInitialForm();
    const form2 = buildInitialForm();

    expect(form1).not.toBe(form2);

    // Mutate form1
    form1.email = 'test@example.com';

    // form2 should be unaffected
    expect(form2.email).toBe('');
  });
});

describe('Integration: Form workflow', () => {
  it('should support typical form initialization and manipulation', () => {
    const form = buildInitialForm();

    // Fill out form fields
    form.email = 'user@example.com';
    form.cvDocId = 'abc123';
    form.jobDescription = 'Senior Developer';

    // Modify channel boost
    const channel = form.preferredYoutubeChannels[0];
    channel.boost = clampBoost(1.5);

    expect(form.email).toBe('user@example.com');
    expect(channel.boost).toBe(1.5);
    expect(formatBoost(channel.boost)).toBe('1.5×');
  });

  it('should support adding new channels', () => {
    const form = buildInitialForm();
    const initialCount = form.preferredYoutubeChannels.length;

    form.preferredYoutubeChannels.push({
      id: generateChannelId(),
      name: 'New Channel',
      boost: clampBoost(1.2),
      isDefault: false,
    });

    expect(form.preferredYoutubeChannels.length).toBe(initialCount + 1);
    expect(form.preferredYoutubeChannels[initialCount].name).toBe('New Channel');
  });

  it('should support removing channels', () => {
    const form = buildInitialForm();
    const initialCount = form.preferredYoutubeChannels.length;

    form.preferredYoutubeChannels.pop();

    expect(form.preferredYoutubeChannels.length).toBe(initialCount - 1);
  });

  it('should maintain channel identity through style computation', () => {
    const form = buildInitialForm();
    const channel = form.preferredYoutubeChannels[0];

    const style1 = computeChipAccent(channel.name);
    const style2 = computeChipAccent(channel.name);

    expect(style1).toEqual(style2);
  });
});