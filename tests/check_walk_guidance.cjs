"use strict";

const assert = require("node:assert/strict");
const walkGuidance = require("../app/static/walk-guidance.js");

async function main() {
  const dogs = [
    { id: 1, name: "Bello", walk_notes: "  Bei Hitze langsam gehen.  " },
    { id: 2, name: "Mila", walk_notes: "  " },
  ];
  let fetchCount = 0;
  const cached = await walkGuidance.load(dogs, async () => {
    fetchCount += 1;
    throw new Error("cached profiles should not fetch");
  });
  assert.equal(fetchCount, 0);
  assert.deepEqual(cached.notes.map(dog => dog.name), ["Bello"]);
  assert.match(walkGuidance.format(cached.notes), /Bello:\nBei Hitze langsam gehen\./);
  assert.match(walkGuidance.format(cached.notes), /hier werden keine Hunde ausgewählt/);

  const fetched = await walkGuidance.load(null, async () => ({ dogs }));
  assert.equal(fetched.error, null);
  assert.deepEqual(fetched.notes.map(dog => dog.name), ["Bello"]);

  assert.equal(walkGuidance.shouldStart([], false), true);
  assert.equal(walkGuidance.shouldStart(cached.notes, false), false);
  assert.equal(walkGuidance.shouldStart(cached.notes, true), true);

  const failed = await walkGuidance.load(null, async () => {
    throw new Error("offline");
  });
  assert.equal(failed.dogs, null);
  assert.equal(failed.notes.length, 0);
  assert.equal(failed.error.message, "offline");
  assert.equal(walkGuidance.shouldStart(failed.notes, false), true);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});