{{flutter_js}}
{{flutter_build_config}}

// No service worker: the demo must always serve the latest build, and waiting for a
// service worker delays first paint by up to 4 s. Unregister any left by older builds.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
}
_flutter.loader.load();
