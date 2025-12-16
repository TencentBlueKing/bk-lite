/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  // Transpile local packages
  transpilePackages: ['@webchat/ui', '@webchat/core'],
};

module.exports = nextConfig;
