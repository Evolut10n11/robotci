// Offline bake of the same reference-pose renderer used for imported descriptions.
import { readFile, writeFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { mergeVertices } from "three/addons/utils/BufferGeometryUtils.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";
import { createDescribedRobot, disposeModel } from "./src/description-model.js";

// GLTFExporter uses browser FileReader for its in-memory binary buffers.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then((result) => { this.result = result; this.onloadend?.(); }); }
  readAsDataURL(blob) { blob.arrayBuffer().then((result) => { this.result = `data:${blob.type};base64,${Buffer.from(result).toString("base64")}`; this.onloadend?.(); }); }
};
const source = path.resolve(process.argv[2]), output = path.resolve(process.argv[3]);
for (const id of ["unitree_go2", "unitree_g1", "franka_emika_panda"]) {
  const description = JSON.parse(await readFile(path.join(output, `${id}.json`), "utf8"));
  const files = new Map();
  for (const name of await readdir(path.join(source, id, "assets"))) {
    const p = path.join(source, id, "assets", name);
    if (!(await stat(p)).isFile()) continue;
    const data = await readFile(p);
    files.set(`assets/${name}`, {
      size: data.length, text: async () => data.toString("utf8"),
      arrayBuffer: async () => data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength),
    });
  }
  const root = await createDescribedRobot(description, { files, useCatalog: false });
  if (root.userData.missingMeshes.length) throw new Error(`Missing model meshes: ${id}`);
  root.traverse((node) => { if (node.geometry) { const old = node.geometry; node.geometry = mergeVertices(old, 1e-8); old.dispose(); } });
  const blob = await new GLTFExporter().parseAsync(root, { binary: true });
  const compressed = gzipSync(Buffer.from(blob), { level: 9 });
  await writeFile(path.join(output, `${id}.glb.gz`), compressed);
  description.geometry = { triangles: root.userData.triangles, dimensions_m: root.userData.dimensions,
    glb_gzip_sha256: createHash("sha256").update(compressed).digest("hex") };
  description.reference_frames = root.userData.referenceFrames;
  await writeFile(path.join(output, `${id}.json`), JSON.stringify(description, null, 2) + "\n");
  console.log(id, description.geometry, "glb bytes", blob.byteLength);
  disposeModel(root);
}
