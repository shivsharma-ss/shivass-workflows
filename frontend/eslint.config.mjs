import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import prettierFlatConfig from 'eslint-config-prettier/flat';
import vitestPlugin from '@vitest/eslint-plugin';

const vitestTestFiles = [
  '**/*.test.{js,jsx,ts,tsx}',
  '**/*.spec.{js,jsx,ts,tsx}',
  '**/__tests__/**/*.{js,jsx,ts,tsx}',
];

const config = [
  ...nextCoreWebVitals,
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
  prettierFlatConfig,
];

export default config;
