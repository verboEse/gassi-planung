"use strict";

const shareToken = decodeURIComponent(location.pathname.split("/").at(-1) || "");
const careFields = [
  ["feeding_instructions", "Fütterung"],
  ["medication_notes", "Medikamente"],
  ["allergies", "Allergien"],
  ["veterinary_contact", "Tierarztkontakt"],
  ["walk_notes", "Gassi-Hinweise"],
];

async function loadDogCare() {
  const status = document.getElementById("guestStatus");
  const container = document.getElementById("guestDogs");
  try {
    const response = await fetch(`/api/dog-care/${encodeURIComponent(shareToken)}`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Der Hundepflege-Link ist ungültig oder wurde widerrufen.");
    const { dogs } = await response.json();
    container.replaceChildren();
    if (!dogs.length) {
      status.textContent = "Es sind keine Hunde hinterlegt.";
      return;
    }
    for (const dog of dogs) {
      const section = document.createElement("section");
      section.className = "card guest-dog";
      const title = document.createElement("h2");
      title.textContent = dog.name;
      section.appendChild(title);
      for (const [field, label] of careFields) {
        if (!dog[field]) continue;
        const detail = document.createElement("div");
        detail.className = "guest-dog-detail";
        const heading = document.createElement("strong");
        heading.textContent = label;
        const value = document.createElement("p");
        value.textContent = dog[field];
        detail.append(heading, value);
        section.appendChild(detail);
      }
      container.appendChild(section);
    }
    status.textContent = "";
  } catch (error) {
    container.replaceChildren();
    status.textContent = error.message;
  }
}

loadDogCare();