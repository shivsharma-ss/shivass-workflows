import { DEFAULT_CHANNEL_SUGGESTIONS } from '../lib/defaultChannels';

export const clampBoost = (value) => {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 1.1;
  }
  return Math.min(2, Math.max(0.5, numeric));
};

export const formatBoost = (value) => {
  const boost = clampBoost(value);
  return `${boost.toFixed(2).replace(/\.00$/, '')}×`;
};

export const generateChannelId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `channel-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export const cloneDefaultChannels = () =>
  DEFAULT_CHANNEL_SUGGESTIONS.map((channel) => ({
    id: generateChannelId(),
    name: channel.name,
    boost: clampBoost(channel.boost ?? 1.1),
    isDefault: Boolean(channel.isDefault),
  }));

export const computeChipAccent = (name) => {
  const subject = (name || 'Creator').toString();
  let hash = 0;
  for (let i = 0; i < subject.length; i += 1) {
    hash = subject.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  const offsetHue = (hue + 28) % 360;
  const chipStyle = {
    background: `linear-gradient(135deg, hsla(${hue}, 70%, 97%, 0.95), hsla(${offsetHue}, 80%, 92%, 0.9))`,
    borderColor: `hsla(${hue}, 70%, 55%, 0.45)`,
  };
  const avatarStyle = {
    background: `linear-gradient(135deg, hsl(${hue}, 75%, 58%), hsl(${offsetHue}, 70%, 52%))`,
    color: '#fff',
  };
  return { chipStyle, avatarStyle };
};

export const buildInitialForm = () => ({
  email: '',
  cvDocId: '',
  jobDescription: '',
  jobDescriptionUrl: '',
  preferredYoutubeChannels: cloneDefaultChannels(),
});
