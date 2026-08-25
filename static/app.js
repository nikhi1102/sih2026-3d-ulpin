/* SIH26011 — 3D ULPIN prototype frontend. Three.js r128, no build step. */

// ---------------------------------------------------------------------
// Geo helpers: lon/lat -> local scene meters (equirectangular, fine at
// neighbourhood scale). Origin is set once the footprints are loaded.
// ---------------------------------------------------------------------
const Geo = {
  origin: null, // {lon, lat}
  setOrigin(lon, lat) { this.origin = { lon, lat }; },
  toLocal(lon, lat) {
    const metersPerDegLat = 110540;
    const metersPerDegLon = 111320 * Math.cos((this.origin.lat * Math.PI) / 180);
    const x = (lon - this.origin.lon) * metersPerDegLon;
    const z = (lat - this.origin.lat) * metersPerDegLat;
    return { x, z };
  },
};

// ---------------------------------------------------------------------
// Three.js scene setup
// ---------------------------------------------------------------------
const container = document.getElementById("scene-container");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0e14);
scene.fog = new THREE.Fog(0x0a0e14, 260, 620);

const camera = new THREE.PerspectiveCamera(
  50,
  window.innerWidth / window.innerHeight,
  0.1,
  2000
);
camera.position.set(90, 110, 140);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI * 0.49;
controls.minDistance = 15;
controls.maxDistance = 500;
controls.target.set(0, 8, 0);

let INITIAL_CAMERA_POS = camera.position.clone();
let INITIAL_TARGET = controls.target.clone();
const CAMERA_OFFSET = new THREE.Vector3(55, 70, 85); // relative to whatever we frame

// Lighting: dark console look, soft ambient + a directional key light.
scene.add(new THREE.AmbientLight(0x8899aa, 0.55));
const keyLight = new THREE.DirectionalLight(0xfff3e0, 0.85);
keyLight.position.set(120, 200, 80);
scene.add(keyLight);
const fillLight = new THREE.DirectionalLight(0x4a6fa5, 0.3);
fillLight.position.set(-100, 80, -120);
scene.add(fillLight);

// Ground plane + grid, "geospatial console" look.
const groundGeo = new THREE.PlaneGeometry(2000, 2000);
const groundMat = new THREE.MeshStandardMaterial({ color: 0x0d1219, roughness: 1 });
const ground = new THREE.Mesh(groundGeo, groundMat);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.05;
scene.add(ground);

const grid = new THREE.GridHelper(2000, 200, 0x1c2b3a, 0x141d28);
grid.position.y = 0;
scene.add(grid);

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

// ---------------------------------------------------------------------
// Small tween helper (no extra deps): eases a value from a->b over ms.
// ---------------------------------------------------------------------
function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}
function tween(durationMs, onUpdate, onComplete) {
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / durationMs);
    onUpdate(easeInOutQuad(t));
    if (t < 1) requestAnimationFrame(step);
    else if (onComplete) onComplete();
  }
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------------
// Building rendering: extrude each footprint polygon to its height.
// ---------------------------------------------------------------------
const COLOR_CONTEXT = 0x5b6b7d;
const COLOR_HERO = 0xf5a623;
const COLOR_OWNED = 0x3ecf8e;
const COLOR_VACANT = 0x4a6fa5;
const EXPLODE_GAP_M = 3.2;
const FLOOR_SLAB_MARGIN = 0.35; // vertical gap left visible between floors
const UNIT_GRID_MARGIN = 0.6; // horizontal gap between units in a floor

const buildingMeshes = new Map(); // building_id -> THREE.Mesh (collapsed solid)

// ---------------------------------------------------------------------
// Procedural facade textures: drawn on a <canvas> at load time, no
// external image files. Keeps the "no internet needed at runtime"
// property of the data layer -- only the Three.js CDN script itself
// needs a network fetch, same as before.
// ---------------------------------------------------------------------
function drawFacadeCanvas(variant) {
  // One window bay per tile -- repeat.x directly controls how many
  // window bays appear around the building, no hidden multiplier.
  const w = 64;
  const h = 256;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  const isHero = variant === "hero";

  ctx.fillStyle = isHero ? "#caa15a" : "#4c5866";
  ctx.fillRect(0, 0, w, h);

  const marginX = w * 0.16;
  const winTop = h * 0.26;
  const winBottom = h * 0.8;
  const frameColor = isHero ? "#8a622b" : "#232d38";
  const glassColor = isHero ? "#3a2c14" : "#18232e";

  const x0 = marginX;
  const x1 = w - marginX;

  ctx.fillStyle = frameColor;
  ctx.fillRect(x0 - 3, winTop - 3, x1 - x0 + 6, winBottom - winTop + 6);

  ctx.fillStyle = glassColor;
  ctx.fillRect(x0, winTop, x1 - x0, winBottom - winTop);

  const grad = ctx.createLinearGradient(x0, winTop, x0, winBottom);
  grad.addColorStop(0, "rgba(255,255,255,0.16)");
  grad.addColorStop(1, "rgba(255,255,255,0.0)");
  ctx.fillStyle = grad;
  ctx.fillRect(x0, winTop, x1 - x0, (winBottom - winTop) * 0.45);

  ctx.strokeStyle = isHero ? "rgba(0,0,0,0.2)" : "rgba(0,0,0,0.25)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, winBottom + 8);
  ctx.lineTo(w, winBottom + 8);
  ctx.stroke();

  return canvas;
}

// ExtrudeGeometry's default side-wall UV generator (WorldUVGenerator, r128)
// uses RAW WORLD-SPACE COORDINATES in meters as the UV values -- it does
// NOT normalize to [0,1] per face. So `texture.repeat` isn't "tiles across
// this wall", it's "tiles per meter": repeat = 1 / (meters per tile) gives
// a fixed real-world window size that's automatically consistent across
// every building regardless of its size, with no per-building math needed.
const FACADE_BAY_WIDTH_M = 3.2; // meters per window bay
const FACADE_FLOOR_HEIGHT_M = 3.0; // meters per texture band vertically

function makeFacadeTexture(variant) {
  const tex = new THREE.CanvasTexture(drawFacadeCanvas(variant));
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1 / FACADE_BAY_WIDTH_M, 1 / FACADE_FLOOR_HEIGHT_M);
  return tex;
}

const HERO_FACADE_BASE = makeFacadeTexture("hero");
const CONTEXT_FACADE_BASE = makeFacadeTexture("context");

function shapeFromRing(ring) {
  // ExtrudeGeometry extrudes along local Z, and we later rotateX(-90deg)
  // to stand it up, which maps shape-Y -> world -Z. Feed it -z here so
  // world Z ends up equal to Geo.toLocal's z directly -- keeping this
  // mesh's world space consistent with localBBoxFromRing() and every
  // other place that positions things from Geo.toLocal (unit grids,
  // camera framing, search fly-to).
  const shape = new THREE.Shape();
  ring.forEach(([lon, lat], i) => {
    const { x, z } = Geo.toLocal(lon, lat);
    if (i === 0) shape.moveTo(x, -z);
    else shape.lineTo(x, -z);
  });
  return shape;
}

function localBBoxFromRing(ring) {
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  ring.forEach(([lon, lat]) => {
    const { x, z } = Geo.toLocal(lon, lat);
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  });
  return { minX, maxX, minZ, maxZ };
}

function buildExtrudedMesh(feature) {
  const ring = feature.geometry.coordinates[0];
  const shape = shapeFromRing(ring);
  const height = feature.properties.height_m;

  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: height,
    bevelEnabled: false,
    steps: 1,
  });
  // ExtrudeGeometry extrudes along local Z; rotate so that becomes world Y (up).
  geometry.rotateX(-Math.PI / 2);

  const isHero = feature.properties.is_hero;

  // ExtrudeGeometry assigns materialIndex 0 to the front/back cap faces
  // and materialIndex 1 to the side (wall) faces -- verified in-browser
  // against r128's actual group output, not just assumed from docs.
  const capMaterial = new THREE.MeshStandardMaterial({
    color: isHero ? 0xb98426 : 0x333c46,
    roughness: 1.0,
    metalness: 0.0,
    transparent: !isHero,
    opacity: isHero ? 1.0 : 0.85,
  });
  const wallMaterial = new THREE.MeshStandardMaterial({
    map: isHero ? HERO_FACADE_BASE : CONTEXT_FACADE_BASE,
    roughness: 0.8,
    metalness: 0.05,
    transparent: !isHero,
    opacity: isHero ? 1.0 : 0.85,
  });

  const mesh = new THREE.Mesh(geometry, [capMaterial, wallMaterial]);
  mesh.userData = { feature, isHeroBase: isHero };
  return mesh;
}

// ---------------------------------------------------------------------
// Hero building: explode into individually-pickable floor/unit boxes.
// ---------------------------------------------------------------------
let heroFeature = null;
let heroMesh = null;
let heroBuildingData = null; // cached GET /api/building/{id} response
let heroFloorsGroup = null; // THREE.Group, built lazily on first explode
let heroExploded = false;
let heroAnimating = false;

const unitMeshByUlpin = new Map();
let selectedUnitMesh = null;

const btnCollapse = document.getElementById("btn-collapse");
const btnReset = document.getElementById("btn-reset");
const hintEl = document.getElementById("hint");

function buildHeroFloorsGroup(data) {
  const ring = data.footprint.coordinates[0];
  const bbox = localBBoxFromRing(ring);
  const group = new THREE.Group();

  data.floors.forEach((floor) => {
    const floorGroup = new THREE.Group();
    floorGroup.position.y = floor.elevation_m; // collapsed position
    floorGroup.userData.collapsedY = floor.elevation_m;
    floorGroup.userData.explodedY = floor.elevation_m + (floor.floor_number - 1) * EXPLODE_GAP_M;

    const n = floor.units.length;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);
    const cellW = (bbox.maxX - bbox.minX) / cols;
    const cellD = (bbox.maxZ - bbox.minZ) / rows;
    const boxH = Math.max(0.4, floor.height_m - FLOOR_SLAB_MARGIN);

    floor.units.forEach((unit, idx) => {
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const cx = bbox.minX + (col + 0.5) * cellW;
      const cz = bbox.minZ + (row + 0.5) * cellD;
      const w = Math.max(0.5, cellW - UNIT_GRID_MARGIN);
      const d = Math.max(0.5, cellD - UNIT_GRID_MARGIN);

      const geo = new THREE.BoxGeometry(w, boxH, d);
      const mat = new THREE.MeshStandardMaterial({
        color: unit.status === "owned" ? COLOR_OWNED : COLOR_VACANT,
        roughness: 0.55,
        metalness: 0.05,
        emissive: 0x000000,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(cx, boxH / 2, cz);
      mesh.userData = { isUnit: true, unit, floor, building: data };
      floorGroup.add(mesh);
      unitMeshByUlpin.set(unit.ulpin, mesh);
    });

    group.add(floorGroup);
  });

  return group;
}

function animateFloorGroups(group, toKey, onComplete) {
  heroAnimating = true;
  const floorGroups = group.children;
  const startYs = floorGroups.map((g) => g.position.y);
  const targetYs = floorGroups.map((g) => g.userData[toKey]);
  tween(
    750,
    (t) => {
      floorGroups.forEach((g, i) => {
        g.position.y = startYs[i] + (targetYs[i] - startYs[i]) * t;
      });
    },
    () => {
      heroAnimating = false;
      if (onComplete) onComplete();
    }
  );
}

async function explodeHero() {
  if (heroAnimating || heroExploded || !heroMesh) return;
  hintEl.textContent = "Loading floors…";
  try {
    if (!heroBuildingData) {
      const res = await fetch(`/api/building/${heroFeature.properties.building_id}`);
      if (!res.ok) throw new Error(`GET /api/building failed: ${res.status}`);
      heroBuildingData = await res.json();
    }
    if (!heroFloorsGroup) {
      heroFloorsGroup = buildHeroFloorsGroup(heroBuildingData);
      scene.add(heroFloorsGroup);
    }
    heroFloorsGroup.visible = true;
    heroMesh.visible = false;
    heroExploded = true;
    btnCollapse.disabled = false;
    animateFloorGroups(heroFloorsGroup, "explodedY", () => {
      hintEl.textContent = "Click a unit for its ULPIN & owner.";
    });
  } catch (err) {
    console.error(err);
    hintEl.textContent = `Error loading building: ${err.message}`;
  }
}

function collapseHero() {
  if (heroAnimating || !heroExploded || !heroFloorsGroup) return;
  closePanel();
  animateFloorGroups(heroFloorsGroup, "collapsedY", () => {
    heroMesh.visible = true;
    heroFloorsGroup.visible = false;
    heroExploded = false;
    btnCollapse.disabled = true;
    hintEl.textContent = "Click the amber hero building to open its floors.";
  });
}

btnCollapse.addEventListener("click", collapseHero);
btnReset.addEventListener("click", () => {
  camera.position.copy(INITIAL_CAMERA_POS);
  controls.target.copy(INITIAL_TARGET);
  controls.update();
});

// ---------------------------------------------------------------------
// Picking (click-to-select, distinguished from orbit-drag)
// ---------------------------------------------------------------------
const raycaster = new THREE.Raycaster();
const pointerNDC = new THREE.Vector2();
let pointerDownPos = null;

renderer.domElement.addEventListener("pointerdown", (e) => {
  pointerDownPos = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!pointerDownPos) return;
  const dx = e.clientX - pointerDownPos.x;
  const dy = e.clientY - pointerDownPos.y;
  pointerDownPos = null;
  if (Math.hypot(dx, dy) > 5) return; // was a drag, not a click
  handleClick(e.clientX, e.clientY);
});

function getPickables() {
  if (heroExploded && heroFloorsGroup) {
    return heroFloorsGroup.children.flatMap((fg) => fg.children);
  }
  return heroMesh ? [heroMesh] : [];
}

function handleClick(clientX, clientY) {
  pointerNDC.x = (clientX / window.innerWidth) * 2 - 1;
  pointerNDC.y = -(clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(pointerNDC, camera);
  const intersects = raycaster.intersectObjects(getPickables(), false);
  if (intersects.length === 0) return;
  const obj = intersects[0].object;
  if (obj.userData.isHeroBase) {
    explodeHero();
  } else if (obj.userData.isUnit) {
    selectUnit(obj);
  }
}

// ---------------------------------------------------------------------
// Side panel
// ---------------------------------------------------------------------
const sidePanel = document.getElementById("side-panel");
const fEls = {
  ulpin: document.getElementById("ulpin-display"),
  floorUnit: document.getElementById("f-floor-unit"),
  area: document.getElementById("f-area"),
  status: document.getElementById("f-status"),
  owner: document.getElementById("f-owner"),
  owntype: document.getElementById("f-owntype"),
  building: document.getElementById("f-building"),
  parcelCode: document.getElementById("f-parcel-code"),
  address: document.getElementById("f-address"),
};

function selectUnit(mesh) {
  if (selectedUnitMesh) selectedUnitMesh.material.emissive.setHex(0x000000);
  selectedUnitMesh = mesh;
  mesh.material.emissive.setHex(0x2a2a2a);
  const { unit, floor, building } = mesh.userData;
  showPanel(unit, floor, building);
}

function showPanel(unit, floor, building) {
  fEls.ulpin.textContent = unit.ulpin_grouped;
  fEls.floorUnit.textContent = `Floor ${floor.floor_number} / Unit ${unit.unit_code}`;
  fEls.area.textContent = `${unit.area_sqm} m²`;
  fEls.status.innerHTML =
    unit.status === "owned"
      ? `Owned <span class="badge badge-owned">Owned</span>`
      : `Vacant <span class="badge badge-vacant">Vacant</span>`;
  fEls.owner.textContent = unit.owner_name || "— (vacant)";
  fEls.owntype.textContent = unit.ownership_type || "—";
  fEls.building.textContent = building.name;
  fEls.parcelCode.textContent = building.parcel.parcel_code;
  fEls.address.textContent = building.parcel.address;
  sidePanel.classList.add("open");
}

function closePanel() {
  sidePanel.classList.remove("open");
  if (selectedUnitMesh) {
    selectedUnitMesh.material.emissive.setHex(0x000000);
    selectedUnitMesh = null;
  }
}
document.getElementById("panel-close").addEventListener("click", closePanel);

// ---------------------------------------------------------------------
// Camera fly-to (used by ULPIN search)
// ---------------------------------------------------------------------
function flyCameraTo(targetVec3, offset, duration = 900) {
  const startCam = camera.position.clone();
  const startTarget = controls.target.clone();
  const endTarget = targetVec3.clone();
  const endCam = endTarget.clone().add(offset);
  tween(duration, (t) => {
    camera.position.lerpVectors(startCam, endCam, t);
    controls.target.lerpVectors(startTarget, endTarget, t);
    controls.update();
  });
}

function flashHighlight(mesh, ms = 1400) {
  // mesh.material may be a single Material (unit boxes) or an array of
  // [capMaterial, wallMaterial] (extruded buildings, since we added the
  // facade texture split) -- handle both.
  const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  mats.forEach((m) => m.emissive.setHex(0x3a2f10));
  setTimeout(() => {
    mats.forEach((m) => m.emissive.setHex(0x000000));
  }, ms);
}

// ---------------------------------------------------------------------
// ULPIN search: fetch /api/unit/{ulpin}, fly to + highlight the match.
// ---------------------------------------------------------------------
const searchInput = document.getElementById("search-input");
const searchStatus = document.getElementById("search-status");

function setSearchStatus(msg, isError) {
  searchStatus.textContent = msg;
  searchStatus.classList.toggle("err", !!isError);
}

function unitDetailToPanelArgs(u) {
  const unit = {
    ulpin_grouped: u.ulpin_grouped,
    unit_code: u.unit_code,
    area_sqm: u.area_sqm,
    status: u.status,
    owner_name: u.owner_name,
    ownership_type: u.ownership_type,
  };
  const floor = { floor_number: u.floor_number, floor_code: u.floor_code };
  const building = { name: u.building_name, parcel: u.parcel };
  return { unit, floor, building };
}

async function flyToAndSelectUnit(u) {
  if (u.is_hero_building) {
    if (!heroExploded) await explodeHero();
    const mesh = unitMeshByUlpin.get(u.ulpin);
    if (!mesh) {
      setSearchStatus("Found the ULPIN, but couldn't locate its unit mesh.", true);
      return;
    }
    const floorGroup = mesh.parent;
    const worldTarget = new THREE.Vector3(
      mesh.position.x,
      floorGroup.userData.explodedY + mesh.position.y,
      mesh.position.z
    );
    flyCameraTo(worldTarget, new THREE.Vector3(16, 18, 24));
    selectUnit(mesh);
  } else {
    const mesh = buildingMeshes.get(u.building_id);
    if (!mesh) {
      setSearchStatus("Found the ULPIN, but couldn't locate its building mesh.", true);
      return;
    }
    mesh.geometry.computeBoundingBox();
    const center = new THREE.Vector3();
    mesh.geometry.boundingBox.getCenter(center);
    flyCameraTo(center, new THREE.Vector3(30, 35, 45));
    flashHighlight(mesh);
    const { unit, floor, building } = unitDetailToPanelArgs(u);
    showPanel(unit, floor, building);
  }
}

async function doSearch() {
  const raw = searchInput.value;
  const digits = raw.replace(/\D/g, "");
  if (digits.length !== 14) {
    setSearchStatus(`ULPIN must be 14 digits (got ${digits.length}).`, true);
    return;
  }
  setSearchStatus("Searching…", false);
  try {
    const res = await fetch(`/api/unit/${digits}`);
    if (res.status === 404) {
      setSearchStatus("No unit found for that ULPIN.", true);
      return;
    }
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const unit = await res.json();
    setSearchStatus(`Found: ${unit.building_name}, Floor ${unit.floor_number} / Unit ${unit.unit_code}`, false);
    await flyToAndSelectUnit(unit);
  } catch (err) {
    console.error(err);
    setSearchStatus(err.message, true);
  }
}

searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});
document.getElementById("search-btn").addEventListener("click", doSearch);

// ---------------------------------------------------------------------
// Load footprints, place all buildings, remember the hero.
// ---------------------------------------------------------------------
async function loadFootprints() {
  const res = await fetch("/api/footprints");
  if (!res.ok) throw new Error(`GET /api/footprints failed: ${res.status}`);
  const fc = await res.json();
  if (!fc.features || fc.features.length === 0) {
    throw new Error("No footprints returned by the API.");
  }

  // Origin = average centroid of the whole dataset (stable, deterministic).
  const lons = fc.features.map((f) => f.properties.centroid[0]);
  const lats = fc.features.map((f) => f.properties.centroid[1]);
  Geo.setOrigin(
    lons.reduce((a, b) => a + b, 0) / lons.length,
    lats.reduce((a, b) => a + b, 0) / lats.length
  );

  for (const feature of fc.features) {
    const mesh = buildExtrudedMesh(feature);
    scene.add(mesh);
    buildingMeshes.set(feature.properties.building_id, mesh);
    if (feature.properties.is_hero) {
      heroFeature = feature;
      heroMesh = mesh;
    }
  }

  // Frame the camera on the hero building so it's visible on first paint.
  // Use the footprint's bbox center rather than its raw vertex-average
  // centroid: for concave (L/U-shaped) footprints the vertex average can
  // land outside the building mass, in a notch, which points the camera
  // at empty space.
  if (heroFeature) {
    const heroRing = heroFeature.geometry.coordinates[0];
    const heroBBox = localBBoxFromRing(heroRing);
    const x = (heroBBox.minX + heroBBox.maxX) / 2;
    const z = (heroBBox.minZ + heroBBox.maxZ) / 2;
    const target = new THREE.Vector3(x, heroFeature.properties.height_m / 2, z);
    INITIAL_TARGET = target;
    INITIAL_CAMERA_POS = target.clone().add(CAMERA_OFFSET);
    camera.position.copy(INITIAL_CAMERA_POS);
    controls.target.copy(INITIAL_TARGET);
    controls.update();
  }

  return fc;
}

const loadingEl = document.getElementById("loading");
const errorEl = document.getElementById("error-banner");

loadFootprints()
  .then((fc) => {
    loadingEl.classList.add("hidden");
    console.log(`Loaded ${fc.features.length} footprints.`);
  })
  .catch((err) => {
    console.error(err);
    loadingEl.classList.add("hidden");
    errorEl.style.display = "block";
    errorEl.textContent = `Failed to load footprints: ${err.message}`;
  });
