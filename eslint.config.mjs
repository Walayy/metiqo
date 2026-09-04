import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/.next/**",
      "coverage/**",
      "node_modules/**",
      "out/**",
      "packages/contracts/src/generated/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [...tseslint.configs.strictTypeChecked, ...tseslint.configs.stylisticTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
