/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    serverComponentsExternalPackages: ["@grpc/grpc-js", "@grpc/proto-loader"],
  },
};

module.exports = nextConfig;