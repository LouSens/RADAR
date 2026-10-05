import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "error",
      // Server state goes through TanStack Query; the one fetch lives in api/client.ts.
      "no-restricted-globals": ["error", { name: "fetch", message: "Use src/api/client.ts." }],
    },
  },
  { files: ["src/api/client.ts"], rules: { "no-restricted-globals": "off" } },
);
