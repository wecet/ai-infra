import globals from 'globals';
import react from 'eslint-plugin-react';

export default [{
  files: ['src/**/*.{js,jsx}', 'tests/**/*.js'],
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: { ...globals.browser, ...globals.node }, parserOptions: { ecmaFeatures: { jsx: true } } },
  plugins: { react },
  rules: { 'no-undef': 'error', 'no-unreachable': 'error', 'react/jsx-no-undef': 'error' },
}];
