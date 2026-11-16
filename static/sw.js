// MedVault's service worker. It exists for one reason: some browsers (Android Chrome
// among them) show a notification only through a service worker, never from the page.
// It caches nothing and intercepts no request. Tapping a notification brings MedVault
// back, or opens it.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || self.registration.scope;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((open) => {
      const app = open.find((client) => client.url.startsWith(new URL(url).origin));
      return app ? app.focus() : self.clients.openWindow(url);
    })
  );
});
