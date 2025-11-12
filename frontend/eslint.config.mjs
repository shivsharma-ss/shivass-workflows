import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import prettierConfig from 'eslint-config-prettier';
import prettierPlugin from 'eslint-plugin-prettier';
import vitestPlugin from '@vitest/eslint-plugin';

const vitestTestFiles = [
  '**/*.test.{js,jsx,ts,tsx}',
  '**/*.spec.{js,jsx,ts,tsx}',
  '**/__tests__/**/*.{js,jsx,ts,tsx}',
];

const config = [
  ...nextCoreWebVitals,
  {
    name: 'prettier',
    plugins: {
      prettier: prettierPlugin,
    },
    rules: {
      ...(prettierConfig?.rules ?? {}),
      'prettier/prettier': 'error',
    },
  },
  {
    name: 'vitest-tests',
    files: vitestTestFiles,
    plugins: {
      '@vitest': vitestPlugin,
    },
    languageOptions: {
      globals: {
        ...vitestPlugin.environments.env.globals,
      },
    },
    rules: {
      '@vitest/no-focused-tests': 'error',
      '@vitest/no-identical-title': 'error',
      '@vitest/expect-expect': 'warn',
    },
  },
];

export default config;
