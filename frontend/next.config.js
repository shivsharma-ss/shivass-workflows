/** @type {import('next').NextConfig} */
const stripTrailingSlash = (value = '') => value.replace(/\/$/, '');

const proxiedApiBase = process.env.API_PROXY_TARGET
  ? stripTrailingSlash(process.env.API_PROXY_TARGET)
  : null;

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (!proxiedApiBase) {
      return [];
    }
    return [
      {
        source: '/v1/:path*',
        destination: `${proxiedApiBase}/v1/:path*`,
      },
      {
        source: '/oauth/:path*',
        destination: `${proxiedApiBase}/oauth/:path*`,
      },
      {
        source: '/review/:path*',
        destination: `${proxiedApiBase}/review/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
