import js from "@eslint/js";
import hooks from "eslint-plugin-react-hooks";
import a11y from "eslint-plugin-jsx-a11y";
import tseslint from "typescript-eslint";
export default [js.configs.recommended,...tseslint.configs.recommended,hooks.configs.flat["recommended-latest"],a11y.flatConfigs.recommended,{ignores:["dist"]}];
