"use strict";

function filterDogsWithWalkNotes(dogs) {
  return dogs.filter(dog =>
    typeof dog.walk_notes === "string" && dog.walk_notes.trim().length > 0
  );
}

async function loadWalkGuidance(currentDogs, fetchDogs) {
  if (currentDogs !== null) {
    return {
      dogs: currentDogs,
      notes: filterDogsWithWalkNotes(currentDogs),
      error: null,
    };
  }
  try {
    const { dogs } = await fetchDogs();
    return { dogs, notes: filterDogsWithWalkNotes(dogs), error: null };
  } catch (error) {
    return { dogs: null, notes: [], error };
  }
}

function formatWalkGuidance(notes) {
  const details = notes
    .map(dog => `${dog.name}:\n${dog.walk_notes.trim()}`)
    .join("\n\n");
  return `Gassi-Hinweise für die Hunde im Haushalt (hier werden keine Hunde ausgewählt):\n\n${details}\n\nGassi-Runde starten?`;
}

function shouldStartWalk(notes, confirmed) {
  return notes.length === 0 || confirmed;
}

const walkGuidance = {
  load: loadWalkGuidance,
  format: formatWalkGuidance,
  shouldStart: shouldStartWalk,
};

if (typeof module === "object" && module.exports) {
  module.exports = walkGuidance;
} else {
  globalThis.walkGuidance = walkGuidance;
}