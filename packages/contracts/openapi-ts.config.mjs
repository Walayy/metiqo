export default {
  input: "./openapi/v1.json",
  output: {
    path: "./src/generated",
  },
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    "@hey-api/sdk",
    "@tanstack/react-query",
  ],
};
