import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
    baseDirectory: __dirname,
});

const eslintConfig = [
    {
        ignores: [
            "node_modules/**",
            ".next/**",
            "out/**",
            "build/**",
            "next-env.d.ts",
            "src-tauri/target/**",
            "public/icon/font/**"
        ]
    },

    ...compat.extends("next", "plugin:@typescript-eslint/recommended"),

    {
        rules: {
            "@typescript-eslint/consistent-type-definitions": ["error", "interface"],
            "@typescript-eslint/no-var-requires": "off",
            "@typescript-eslint/no-non-null-assertion": "off",
            "@typescript-eslint/no-explicit-any": "off",
            "@typescript-eslint/no-unused-vars": ["error", {
                argsIgnorePattern: "^_",
                varsIgnorePattern: "^_"
            }],
            "@typescript-eslint/no-unused-expressions": ["error", {
                allowShortCircuit: true
            }],
            "no-console": "off",
            "prefer-const": "error",
            "no-debugger": "error",
            "react-hooks/exhaustive-deps": "off",
            "react/display-name": "warn",
            "react/no-unescaped-entities": "off",
            "@next/next/no-img-element": "off"
        }
    }
];

export default eslintConfig;
