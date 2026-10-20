import "/node_modules/feather-icons/dist/feather.js";

const featherGlobal = globalThis.feather ?? globalThis.window?.feather ?? {};

const feather = {
  ...featherGlobal,
  icons: featherGlobal.icons ?? {},
};

export default feather;
