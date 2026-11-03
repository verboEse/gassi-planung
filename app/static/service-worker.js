"use strict";

self.addEventListener("push", event => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch { /* use the default reminder */ }
  event.waitUntil(self.registration.showNotification(
    payload.title || "Gassi-Erinnerung",
    {
      body: payload.body || "In 15 Minuten ist deine Gassirunde.",
      tag: payload.tag,
    },
  ));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow("/"));
});
