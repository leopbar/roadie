import type { NextConfig } from "next";

// Para onde o console fala com a API. Dentro do Docker Compose o serviço
// chama-se "api"; rodando o Next fora do Docker, aponte para a porta local.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // O navegador só conhece /api/*: cookies ficam no mesmo domínio e não há CORS.
    return [{ source: "/api/:path*", destination: `${apiInternalUrl}/:path*` }];
  },
};

export default nextConfig;
