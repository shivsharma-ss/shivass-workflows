import { DEFAULT_CHANNEL_SUGGESTIONS } from '../lib/defaultChannels';

test('default channel suggestions have unique names and sane boosts', () => {
  const names = DEFAULT_CHANNEL_SUGGESTIONS.map((item) => item.name.trim());
  expect(new Set(names).size).toBe(names.length);
  DEFAULT_CHANNEL_SUGGESTIONS.forEach((channel) => {
    expect(channel.boost).toBeGreaterThan(0);
    expect(channel.isDefault).toBe(true);
  });
});
