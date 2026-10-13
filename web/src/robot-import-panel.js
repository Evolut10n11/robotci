import { createDescribedRobot, disposeModel, normalizeLocalPath } from "./description-model.js";

const LABELS = { quadruped: "Четвероногий робот", humanoid: "Гуманоид", manipulator: "Манипулятор", wheeled: "Колёсная платформа", unknown: "Тип не определён" };
let catalogPromise;
export function getModelCatalog() {
  if (!catalogPromise) catalogPromise = fetch("/api/robot-model/catalog", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error("Импорт доступен через локальный сервер RobotCI."); return r.json(); })
    .catch((e) => { catalogPromise = null; throw e; });
  return catalogPromise;
}
export async function inspectRobotText(text) {
  const catalog = await getModelCatalog();
  const response = await fetch("/api/robot-model/inspect", { method: "POST", headers: {
    "Content-Type": "application/json", "X-RobotCI-Model-Token": catalog.token,
  }, body: JSON.stringify({ text }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Не удалось прочитать описание.");
  return result;
}
export async function loadCatalogRobot(id) {
  const description = await inspectRobotText(`robot:\n  model: ${id}\n`);
  const model = await createDescribedRobot(description);
  return { description, model };
}

export function openRobotImport({ onApply }) {
  let dialog = document.getElementById("robot-import-dialog");
  if (dialog) { dialog.showModal(); return; }
  dialog = document.createElement("dialog"); dialog.id = "robot-import-dialog";
  dialog.className = "robot-import-dialog"; dialog.setAttribute("aria-labelledby", "robot-import-title");
  // Only static markup here. User descriptions, labels and errors always use textContent.
  dialog.innerHTML = `
    <div class="dialog-heading"><div><p class="eyebrow">ОПИСАНИЕ И ГЕОМЕТРИЯ</p><h2 id="robot-import-title">Добавить своего робота</h2></div><button type="button" class="icon-button" id="robot-import-close" aria-label="Закрыть импорт робота">×</button></div>
    <p class="dialog-intro">Вставьте URDF, MJCF или YAML с <code>robot.model</code>. Описание обрабатывается локально; код и плагины не запускаются.</p>
    <div class="robot-preset-row" role="group" aria-label="Встроенные реальные модели"><button type="button" class="button small" data-robot-preset="unitree_go2">Unitree Go2</button><button type="button" class="button small" data-robot-preset="unitree_g1">Unitree G1</button><button type="button" class="button small" data-robot-preset="franka_emika_panda">Franka Panda</button></div>
    <label class="file-field"><span>Файл описания</span><input id="robot-description-file" type="file" accept=".urdf,.xml,.yaml,.yml" /></label>
    <label class="file-field"><span>Папка с описанием и мешами <small>Необязательно</small></span><input id="robot-description-folder" type="file" webkitdirectory multiple /><span class="file-hint">Для своих мешей: OBJ или STL. Файлы остаются в браузере; сетевые ссылки не загружаются.</span></label>
    <label class="robot-entry-label" hidden><span>Описание в выбранной папке</span><select id="robot-description-entry"></select></label>
    <label class="robot-text-label"><span>Конфигурация или описание</span><textarea id="robot-description-text" rows="8" spellcheck="false" aria-label="Конфигурация или описание робота"></textarea></label>
    <p class="notice" id="robot-import-status" role="status" hidden></p>
    <div id="robot-import-result" class="robot-import-result" hidden></div>
    <p class="microcopy">Модель отображается в опорной позе. Это не обученный контроллер и не доказательство поддержки робота симулятором. В 2D остаётся условный маркер.</p>
    <div class="dialog-actions"><button type="button" class="button" id="robot-import-cancel">Закрыть</button><button type="button" class="button primary" id="robot-import-apply">Распознать и встроить</button></div>`;
  document.body.append(dialog);
  const q = (id) => dialog.querySelector(`#${id}`);
  let files = new Map(), base = "", busy = false, serial = 0;
  function status(message, error = false) {
    q("robot-import-status").textContent = message;
    q("robot-import-status").hidden = !message;
    q("robot-import-status").classList.toggle("error", error);
  }
  function close() { serial++; dialog.close(); dialog.remove(); files.clear(); }
  q("robot-import-close").onclick = close; q("robot-import-cancel").onclick = close;
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  const text = q("robot-description-text");
  async function read(file) {
    if (file.size > 2 * 1024 * 1024) throw new Error("Описание превышает 2 МиБ.");
    text.value = await file.text();
    const path = file.webkitRelativePath || file.name;
    base = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  }
  q("robot-description-file").onchange = async (event) => {
    const file = event.target.files[0]; if (!file) return;
    try { await read(file); status("Описание загружено. Нажмите «Распознать и встроить»."); }
    catch (error) { status(error.message, true); }
  };
  q("robot-description-folder").onchange = async (event) => {
    try {
      const selected = [...event.target.files];
      if (selected.length > 512 || selected.reduce((sum, f) => sum + f.size, 0) > 128 * 1024 * 1024)
        throw new Error("Папка превышает лимит: 512 файлов или 128 МиБ.");
      const next = new Map();
      for (const file of selected) next.set(normalizeLocalPath(file.webkitRelativePath || file.name), file);
      const entries = selected.filter((f) => /\.(urdf|xml|ya?ml)$/i.test(f.name));
      if (!entries.length) throw new Error("В папке нет URDF, XML или YAML.");
      files = next;
      entries.sort((a, b) => Number(/^(go2|g1|panda)\.xml$/i.test(b.name) || /\.urdf$/i.test(b.name)) - Number(/^(go2|g1|panda)\.xml$/i.test(a.name) || /\.urdf$/i.test(a.name)));
      const selector = q("robot-description-entry"); selector.replaceChildren();
      for (const file of entries) { const o = document.createElement("option"); o.textContent = file.webkitRelativePath; o.value = file.webkitRelativePath; selector.append(o); }
      selector.parentElement.hidden = false;
      selector.onchange = () => read(files.get(selector.value)).catch((error) => status(error.message, true));
      await read(entries[0]); status(`Выбрано ${selected.length} локальных файлов. Проверьте главный файл описания.`);
    } catch (error) { status(error.message, true); }
  };
  dialog.querySelectorAll("[data-robot-preset]").forEach((button) => button.onclick = () => {
    text.value = `robot:\n  model: ${button.dataset.robotPreset}\n`; base = "";
  });
  q("robot-import-apply").onclick = async () => {
    if (busy) return;
    busy = true; const version = ++serial;
    q("robot-import-apply").disabled = true;
    const inputs = [...dialog.querySelectorAll("input, textarea, select, [data-robot-preset]")];
    inputs.forEach((input) => { input.disabled = true; });
    let loaded;
    try {
      status("Читаю структуру и собираю геометрию…");
      const sourceText = text.value, selectedFiles = new Map(files), sourceBase = base;
      const description = await inspectRobotText(sourceText);
      loaded = await createDescribedRobot(description, { files: selectedFiles, base: sourceBase });
      if (version !== serial || !dialog.isConnected) { disposeModel(loaded); return; }
      const c = description.classification, missing = loaded.userData.missingMeshes;
      const summary = `${description.name} · ${LABELS[c.kind]} · ${description.link_count} звеньев · ${description.joint_count} суставов`;
      const detail = description.identification === "exact_catalog_description" ? "Точное совпадение с описанием из закреплённого каталога." : description.identification === "declared_catalog" ? "Модель явно выбрана из локального каталога." : `${c.reasons.join(" ")} Уверенность: ${{ high: "высокая", medium: "средняя", low: "низкая" }[c.confidence]}.`;
      const result = q("robot-import-result"); result.replaceChildren(); result.hidden = false;
      for (const line of [summary, detail, ...description.warnings, ...(missing.length ? [`Не найдены или не поддержаны меши (${missing.length}): ${missing.slice(0, 6).join(", ")}. Показаны доступная геометрия и кинематический каркас, не точная оболочка.`] : [])]) {
        const p = document.createElement("p"); p.textContent = line; result.append(p);
      }
      await onApply({ description, model: loaded }); loaded = null;
      status("Робот встроен в 3D. Закройте окно, чтобы осмотреть модель. Записи и вердикт не изменены.");
    } catch (error) { disposeModel(loaded); if (version === serial) status(error.message, true); }
    finally {
      busy = false;
      if (dialog.isConnected) {
        q("robot-import-apply").disabled = false;
        inputs.forEach((input) => { input.disabled = false; });
      }
    }
  };
  dialog.showModal(); text.focus();
}
