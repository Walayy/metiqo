import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  ...(process.env.NEXT_STANDALONE === "true" ? { output: "standalone" as const } : {}),
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@metiquo/contracts", "@metiquo/ui"],
};

export default nextConfig;
