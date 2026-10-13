"""Bounded, offline robot-description inspection. Never launches a robot or evaluates code.

The returned tree is a reference-pose visualization, NOT dynamics or a navigation
result. Meshes remain references to explicitly selected local files. Unsupported
constructs fail clearly instead of silently producing a different robot.
"""

from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from robotci.model_mimic import resolve_mimic_reference

MAX_DESCRIPTION_BYTES = 2 * 1024 * 1024
MAX_NODES = 256
MAX_ELEMENTS = 8000
MAX_DEPTH = 48
CATALOG_DIR = Path(__file__).with_name("model_catalog")
CATALOG = {
    "unitree_go2": {"label": "Unitree Go2", "kind": "quadruped", "profile": "quadruped"},
    "unitree_g1": {"label": "Unitree G1", "kind": "humanoid", "profile": "humanoid"},
    "franka_emika_panda": {
        "label": "Franka Emika Panda",
        "kind": "manipulator",
        "profile": "rover",
    },
}


class ModelImportError(ValueError):
    """An incomplete, unsupported or unsafe description was not imported."""


def _numbers(text: str | None, count: int, default: list[float]) -> list[float]:
    if text is None:
        if len(default) != count:
            raise ModelImportError("В описании отсутствует обязательное число или размер.")
        return list(default)
    try:
        values = [float(x) for x in text.split()]
    except (ValueError, OverflowError) as exc:
        raise ModelImportError("Неверное числовое значение в описании робота.") from exc
    if len(values) != count or any(not math.isfinite(x) or abs(x) > 10000 for x in values):
        raise ModelImportError(f"Ожидалось {count} конечных чисел в допустимом диапазоне.")
    return values


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values))
    if norm < 1e-12:
        raise ModelImportError("Нулевая ось или нулевой кватернион.")
    return [x / norm for x in values]


def _qmul(a: list[float], b: list[float]) -> list[float]:
    x, y, z, w = a
    X, Y, Z, W = b
    return [
        w * X + x * W + y * Z - z * Y,
        w * Y - x * Z + y * W + z * X,
        w * Z + x * Y - y * X + z * W,
        w * W - x * X - y * Y - z * Z,
    ]


def _axis_quat(axis: list[float], angle: float) -> list[float]:
    axis = _unit(axis)
    return [*(x * math.sin(angle / 2) for x in axis), math.cos(angle / 2)]


def _rotation(a: dict[str, str], factor: float = 1.0, seq: str = "xyz") -> list[float]:
    present = [key for key in ("quat", "euler", "axisangle", "xyaxes", "zaxis") if key in a]
    if len(present) > 1:
        raise ModelImportError("Несколько способов задания ориентации одновременно.")
    if "quat" in a:
        w, x, y, z = _numbers(a["quat"], 4, [])
        return _unit([x, y, z, w])
    if "axisangle" in a:
        x, y, z, angle = _numbers(a["axisangle"], 4, [])
        return _axis_quat([x, y, z], angle * factor)
    if "xyaxes" in a or "zaxis" in a:
        raise ModelImportError("Ориентации xyaxes/zaxis пока не поддержаны; используйте quat.")
    angles = _numbers(a.get("euler"), 3, [0, 0, 0])
    q = [0.0, 0.0, 0.0, 1.0]
    for ch, angle in zip(seq, angles, strict=True):
        axis = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[ch.lower()]
        rot = _axis_quat(axis, angle * factor)
        q = _qmul(q, rot) if ch.islower() else _qmul(rot, q)
    return q


def _name(value: str | None, fallback: str = "") -> str:
    value = value or fallback
    if not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ModelImportError("Имя должно содержать от 1 до 256 печатных символов.")
    return value


def _local_path(value: str) -> str:
    if (
        not value
        or len(value) > 512
        or "\\" in value
        or value.startswith("/")
        or re.match(r"^[a-zA-Z]:", value)
        or any(ord(c) < 32 for c in value)
    ):
        raise ModelImportError("Нужен относительный путь к выбранному локальному файлу.")
    if ":" in value and not value.startswith("package://"):
        raise ModelImportError("Сетевые и file:// ссылки не загружаются.")
    return value


def _parse_xml(text: str) -> ET.Element:
    if len(text.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ModelImportError("Описание превышает 2 МиБ.")
    if re.search(
        r"<!\s*(?:DOCTYPE|ENTITY)|<\?|\$\{|\$\(", re.sub(r"^\s*<\?xml[^?]*\?>", "", text), re.I
    ):
        raise ModelImportError(
            "DTD, сущности, инструкции и Xacro не выполняются. Нужен готовый XML."
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ModelImportError("Некорректный XML описания робота.") from exc
    stack = [(root, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise ModelImportError("Описание слишком большое или слишком глубоко вложено.")
        if ":" in node.tag or "}" in node.tag:
            raise ModelImportError("XML-пространства имён и Xacro пока не поддержаны.")
        if len(node.attrib) > 32 or any(len(v) > 128_000 for v in node.attrib.values()):
            raise ModelImportError("Превышен лимит атрибутов XML.")
        stack.extend((child, depth + 1) for child in node)
    return root


def _origin(node: ET.Element | None) -> tuple[list[float], list[float]]:
    a = node.attrib if node is not None else {}
    return (
        _numbers(a.get("xyz"), 3, [0, 0, 0]),
        _rotation({"euler": a.get("rpy", "0 0 0")}, seq="XYZ"),
    )


def _positive(size: list[float]) -> list[float]:
    if any(x <= 0 or x > 100 for x in size):
        raise ModelImportError("Размеры и масштаб должны быть положительными, не более 100 м.")
    return size


def _color(value: str | None) -> list[float]:
    rgba = _numbers(value, 4, [0.65, 0.7, 0.76, 1])
    if any(x < 0 or x > 1 for x in rgba):
        raise ModelImportError("Цвет rgba должен находиться в диапазоне 0..1.")
    return rgba


def _urdf(root: ET.Element, warnings: list[str]) -> list[dict[str, Any]]:
    if root.find(".//gazebo") is not None:
        warnings.append("Плагины и настройки Gazebo не выполнялись.")
    materials = {}
    for material in root.findall("material"):
        color = material.find("color")
        if color is not None:
            materials[_name(material.get("name"))] = _color(color.get("rgba"))
    nodes: dict[str, dict[str, Any]] = {}
    for link in root.findall("link"):
        name = _name(link.get("name"))
        if name in nodes:
            raise ModelImportError("Повтор имени звена URDF.")
        shapes = []
        for visual in link.findall("visual"):
            geometry = visual.find("geometry")
            if geometry is None or len(geometry) != 1:
                raise ModelImportError("В visual нужна одна geometry.")
            shape = geometry[0]
            kind = shape.tag
            pos, quat = _origin(visual.find("origin"))
            item: dict[str, Any] = {"type": kind, "pos": pos, "quat": quat}
            if kind == "box":
                item["size"] = _positive(_numbers(shape.get("size"), 3, []))
            elif kind == "sphere":
                item["size"] = _positive(_numbers(shape.get("radius"), 1, []))
            elif kind == "cylinder":
                item["size"] = _positive(
                    [
                        *_numbers(shape.get("radius"), 1, []),
                        *_numbers(shape.get("length"), 1, []),
                    ]
                )
            elif kind == "mesh":
                item["file"] = _local_path(shape.get("filename", ""))
                item["scale"] = _positive(_numbers(shape.get("scale"), 3, [1, 1, 1]))
            else:
                raise ModelImportError(f"Геометрия URDF не поддержана: {kind}.")
            material = visual.find("material")
            color = material.find("color") if material is not None else None
            item["rgba"] = (
                _color(color.get("rgba"))
                if color is not None
                else materials.get(material.get("name"), _color(None))
                if material is not None
                else _color(None)
            )
            if material is not None and material.find("texture") is not None:
                warnings.append("Текстуры URDF пока не загружаются; сохранён цвет материала.")
            shapes.append(item)
        nodes[name] = {
            "name": name,
            "parent": None,
            "pos": [0, 0, 0],
            "quat": [0, 0, 0, 1],
            "joints": [],
            "visuals": shapes,
        }
    names = set()
    for joint in root.findall("joint"):
        name = _name(joint.get("name"))
        if name in names:
            raise ModelImportError("Повтор имени сустава URDF.")
        names.add(name)
        parent, child = joint.find("parent"), joint.find("child")
        if parent is None or child is None:
            raise ModelImportError("У сустава отсутствует parent или child.")
        p, c = parent.get("link"), child.get("link")
        if p not in nodes or c not in nodes or p == c or nodes[c]["parent"] is not None:
            raise ModelImportError("Неверная связь звеньев URDF.")
        kind = joint.get("type")
        if kind not in {"fixed", "revolute", "continuous", "prismatic"}:
            raise ModelImportError("URDF preview поддерживает fixed/revolute/continuous/prismatic.")
        nodes[c]["parent"] = p
        nodes[c]["pos"], nodes[c]["quat"] = _origin(joint.find("origin"))
        if kind != "fixed":
            axis = joint.find("axis")
            limit = joint.find("limit")
            limits = None
            if kind in {"revolute", "prismatic"}:
                if limit is None or "lower" not in limit.attrib or "upper" not in limit.attrib:
                    raise ModelImportError("У ограниченного сустава отсутствуют lower/upper.")
                limits = [_numbers(limit.get(k), 1, [])[0] for k in ("lower", "upper")]
                if limits[0] > limits[1]:
                    raise ModelImportError("Нижний предел сустава больше верхнего.")
            value = min(max(0, limits[0]), limits[1]) if limits else 0
            nodes[c]["joints"] = [
                {
                    "name": name,
                    "type": kind,
                    "pos": [0, 0, 0],
                    "axis": _unit(
                        _numbers(axis.get("xyz") if axis is not None else None, 3, [1, 0, 0])
                    ),
                    "range": limits,
                    "value": value,
                    "ref": 0,
                }
            ]
        mimics = joint.findall("mimic")
        if mimics:
            if len(mimics) != 1 or kind == "fixed":
                raise ModelImportError("Нужен один mimic у подвижного скалярного сустава.")
            mimic = mimics[0]
            if len(mimic) or set(mimic.attrib) - {"joint", "multiplier", "offset"}:
                raise ModelImportError("Неподдерживаемые атрибуты или вложения mimic.")
            nodes[c]["joints"][0]["mimic"] = {
                "joint": _name(mimic.get("joint")),
                "multiplier": _numbers(mimic.get("multiplier"), 1, [1])[0],
                "offset": _numbers(mimic.get("offset"), 1, [0])[0],
            }
    result = list(nodes.values())
    _validate_tree(result)
    try:
        mimic_count = resolve_mimic_reference(result, max_depth=MAX_DEPTH)
    except ValueError as exc:
        raise ModelImportError(str(exc)) from exc
    if mimic_count:
        warnings.append(
            f"Связанных mimic-суставов: {mimic_count}. Опорная поза учитывает связи и пределы; "
            "это не записанное движение или контроллер."
        )
    return result


def _mjcf(root: ET.Element, warnings: list[str]) -> list[dict[str, Any]]:
    for tag in (
        "include",
        "frame",
        "attach",
        "composite",
        "flex",
        "flexcomp",
        "replicate",
        "plugin",
    ):
        if root.find(f".//{tag}") is not None:
            raise ModelImportError(
                f"MJCF {tag} не поддержан в этом preview; нужен развёрнутый файл."
            )
    compiler = root.find("compiler")
    a = compiler.attrib if compiler is not None else {}
    if a.get("coordinate", "local") != "local" or a.get("strippath", "false") != "false":
        raise ModelImportError("MJCF coordinate/strippath требуют предварительного развёртывания.")
    angle = a.get("angle", "degree")
    if angle not in {"radian", "degree"}:
        raise ModelImportError("Неизвестная единица углов MJCF.")
    factor = math.pi / 180 if angle == "degree" else 1.0
    seq = a.get("eulerseq", "xyz")
    if len(seq) != 3 or any(x not in "xyzXYZ" for x in seq):
        raise ModelImportError("Неверная последовательность углов MJCF.")
    meshdir = a.get("meshdir", a.get("assetdir", ""))
    if meshdir:
        _local_path(meshdir)
    defaults: dict[str, dict[str, dict[str, str]]] = {"main": {}}

    def default(node: ET.Element, inherited: dict[str, dict[str, str]]) -> None:
        name = node.get("class", "main")
        if name in defaults and name != "main":
            raise ModelImportError("Повтор класса default MJCF.")
        values = {k: dict(v) for k, v in inherited.items()}
        for child in node:
            if child.tag != "default":
                values[child.tag] = {**values.get(child.tag, {}), **child.attrib}
        defaults[name] = values
        for child in node.findall("default"):
            default(child, values)

    for node in root.findall("default"):
        default(node, defaults["main"])

    def attributes(node: ET.Element, parentclass: str) -> dict[str, str]:
        cls = node.get("class", parentclass)
        if cls not in defaults:
            raise ModelImportError("Неизвестный default-класс MJCF.")
        return {**defaults[cls].get(node.tag, {}), **node.attrib}

    meshes, materials = {}, {}
    for mesh in root.findall("asset/mesh"):
        item = attributes(mesh, "main")
        file = item.get("file")
        if file is None:
            raise ModelImportError("Встроенные vertex-меши MJCF пока не поддержаны.")
        name = item.get("name", posixpath.splitext(posixpath.basename(file))[0])
        if name in meshes:
            raise ModelImportError("Повтор имени mesh MJCF.")
        meshes[name] = {
            "file": _local_path(posixpath.join(meshdir, file)),
            "scale": _positive(_numbers(item.get("scale"), 3, [1, 1, 1])),
        }
    for material in root.findall("asset/material"):
        item = attributes(material, "main")
        materials[_name(item.get("name"))] = _color(item.get("rgba"))
    world = root.find("worldbody")
    if world is None:
        raise ModelImportError("MJCF не содержит worldbody; одного файла сцены недостаточно.")
    nodes = []
    qpos_slots: list[tuple[dict[str, Any], int, str]] = []
    jointnames = set()

    def body(element: ET.Element, parent: str | None, inherited: str) -> None:
        if len(nodes) >= MAX_NODES:
            raise ModelImportError("Слишком много звеньев.")
        cls = element.get("childclass", inherited)
        name = _name(element.get("name"), f"body_{len(nodes)}")
        node: dict[str, Any] = {
            "name": name,
            "parent": parent,
            "pos": _numbers(element.get("pos"), 3, [0, 0, 0]),
            "quat": _rotation(element.attrib, factor, seq),
            "joints": [],
            "visuals": [],
        }
        nodes.append(node)
        joints = [x for x in element if x.tag in {"joint", "freejoint"}]
        for index, joint in enumerate(joints):
            j = attributes(joint, cls)
            kind = "free" if joint.tag == "freejoint" else j.get("type", "hinge")
            if kind == "free":
                if parent is not None or len(joints) != 1:
                    raise ModelImportError("freejoint разрешён только у одного корневого тела.")
                qpos_slots.append((node, 7, "free"))
                node["floating_base"] = True
                continue
            if kind not in {"hinge", "slide"}:
                raise ModelImportError("MJCF preview пока поддерживает hinge/slide/freejoint.")
            jname = _name(j.get("name"), f"{name}_joint_{index}")
            if jname in jointnames:
                raise ModelImportError("Повтор имени сустава MJCF.")
            jointnames.add(jname)
            limits = _numbers(j["range"], 2, []) if "range" in j else None
            unit = factor if kind == "hinge" else 1.0
            if limits:
                limits = [x * unit for x in limits]
                if limits[0] > limits[1]:
                    raise ModelImportError("Неверные пределы сустава MJCF.")
            ref = _numbers(j.get("ref"), 1, [0])[0] * unit
            record = {
                "name": jname,
                "type": "revolute" if kind == "hinge" else "prismatic",
                "pos": _numbers(j.get("pos"), 3, [0, 0, 0]),
                "axis": _unit(_numbers(j.get("axis"), 3, [0, 0, 1])),
                "range": limits if j.get("limited") != "false" else None,
                "value": ref,
                "ref": ref,
            }
            node["joints"].append(record)
            qpos_slots.append((record, 1, kind))
        shapes = []
        for geom in element.findall("geom"):
            g = attributes(geom, cls)
            kind = g.get("type", "mesh" if "mesh" in g else "sphere")
            item: dict[str, Any] = {
                "type": kind,
                "pos": _numbers(g.get("pos"), 3, [0, 0, 0]),
                "quat": _rotation(g, factor, seq),
                "rgba": _color(g["rgba"])
                if "rgba" in g
                else materials.get(g.get("material"), _color(None)),
                "collision": g.get("group", "0") == "3",
            }
            if kind == "mesh":
                if g.get("mesh") not in meshes:
                    raise ModelImportError("Геометрия ссылается на отсутствующий mesh.")
                item.update(meshes[g["mesh"]])
            elif kind in {"box", "ellipsoid"}:
                item["size"] = [2 * x for x in _positive(_numbers(g.get("size"), 3, []))]
            elif kind == "sphere":
                item["size"] = _positive(_numbers(g.get("size"), 1, []))
            elif kind in {"capsule", "cylinder"}:
                if "fromto" in g:
                    points = _numbers(g["fromto"], 6, [])
                    delta = [points[i + 3] - points[i] for i in range(3)]
                    length = math.sqrt(sum(x * x for x in delta))
                    if length < 1e-9:
                        raise ModelImportError("Нулевая длина fromto.")
                    x, y, z = [d / length for d in delta]
                    item["quat"] = [1, 0, 0, 0] if z < -0.999999999 else _unit([-y, x, 0, 1 + z])
                    item["pos"] = [(points[i] + points[i + 3]) / 2 for i in range(3)]
                    size = g.get("size", "").split()
                    item["size"] = _positive([*_numbers(size[0] if size else None, 1, []), length])
                else:
                    radius, half = _positive(_numbers(g.get("size"), 2, []))
                    item["size"] = [radius, 2 * half]
            else:
                raise ModelImportError(f"Геометрия MJCF не поддержана: {kind}.")
            shapes.append(item)
        node["visuals"] = shapes
        for child in element.findall("body"):
            body(child, name, cls)

    for item in world.findall("body"):
        body(item, None, "main")
    keys = root.findall("keyframe/key")
    key = next((k for k in keys if k.get("name") in {"home", "stand"}), None)
    if key is not None and "qpos" in key.attrib:
        # qpos is an mjData state vector: radians even when XML angles use degrees.
        values = _numbers(key.get("qpos"), sum(n for _, n, _ in qpos_slots), [])
        offset = 0
        for record, n, kind in qpos_slots:
            val = values[offset : offset + n]
            if kind == "free":
                record["pos"], record["quat"] = val[:3], _unit(val[4:] + [val[3]])
            else:
                record["value"] = val[0]
            offset += n
        warnings.append(
            "Показана опорная поза home/stand из MJCF, не записанное движение суставов."
        )
    else:
        warnings.append("Показана исходная поза описания, не записанное движение суставов.")
    if root.find("equality") is not None or root.find("tendon") is not None:
        warnings.append("Equality/tendon-ограничения не решаются в статическом предпросмотре.")
    return nodes


def _validate_tree(nodes: list[dict[str, Any]]) -> None:
    if not nodes or len(nodes) > MAX_NODES:
        raise ModelImportError("Нужно от 1 до 256 звеньев.")
    mapping = {node["name"]: node for node in nodes}
    if len(mapping) != len(nodes):
        raise ModelImportError("Имена звеньев должны быть уникальны.")
    roots = [node for node in nodes if node["parent"] is None]
    if len(roots) != 1:
        raise ModelImportError("Нужно одно связное дерево робота с одним корневым звеном.")
    for node in nodes:
        seen = set()
        while node["parent"] is not None:
            if node["name"] in seen or len(seen) > MAX_DEPTH:
                raise ModelImportError("Цикл или слишком глубокое дерево звеньев.")
            seen.add(node["name"])
            if node["parent"] not in mapping:
                raise ModelImportError("Ссылка на неизвестное звено.")
            node = mapping[node["parent"]]


def classify(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Conservative structural heuristics. Confidence tiers are not probabilities."""
    joints = [j for node in nodes for j in node["joints"]]
    names = [j["name"].lower() for j in joints]
    wheels = [n for n in names if "wheel" in n]
    knees = [n for n in names if "knee" in n or "calf" in n]
    shoulders = [n for n in names if "shoulder" in n]
    hips = [n for n in names if "hip" in n]
    mapping = {n["name"]: n for n in nodes}

    def branch(node: dict[str, Any]) -> str:
        while node["parent"] is not None and mapping[node["parent"]]["parent"] is not None:
            node = mapping[node["parent"]]
        return node["name"]

    knee_branches = {
        branch(n)
        for n in nodes
        for j in n["joints"]
        if "knee" in j["name"].lower() or "calf" in j["name"].lower()
    }
    shoulder_branches = {
        branch(n) for n in nodes for j in n["joints"] if "shoulder" in j["name"].lower()
    }
    depths = []
    for node in nodes:
        depth = len(node["joints"])
        while node["parent"] is not None:
            node = mapping[node["parent"]]
            depth += len(node["joints"])
        depths.append(depth)
    if len(wheels) >= 2:
        kind, profile, confidence, reason = (
            "wheeled",
            "rover",
            "medium",
            "Найдены несколько суставов колёс.",
        )
    elif len(knees) == 4 and len(knee_branches) == 4 and len(hips) >= 4 and len(joints) >= 12:
        kind, profile, confidence, reason = (
            "quadruped",
            "quadruped",
            "high",
            "Найдены четыре коленных и тазобедренных цепочки.",
        )
    elif (
        len(knees) == 2
        and len(knee_branches) == 2
        and len(hips) >= 2
        and len(shoulders) >= 2
        and bool(shoulder_branches - knee_branches)
        and len(joints) >= 12
    ):
        kind, profile, confidence, reason = (
            "humanoid",
            "humanoid",
            "high",
            "Найдены две ноги и две плечевые цепочки.",
        )
    elif max(depths, default=0) >= 5 and not any(n.get("floating_base") for n in nodes):
        kind, profile, confidence, reason = (
            "manipulator",
            "rover",
            "medium",
            "Обнаружена длинная последовательная цепь суставов.",
        )
    else:
        kind, profile, confidence, reason = (
            "unknown",
            "rover",
            "low",
            "Структуры недостаточно для уверенного определения типа.",
        )
    return {"kind": kind, "profile": profile, "confidence": confidence, "reasons": [reason]}


def catalog_model(model_id: str) -> dict[str, Any]:
    if model_id not in CATALOG:
        raise ModelImportError(
            "Неизвестная модель. Поддержаны unitree_go2, unitree_g1, franka_emika_panda."
        )
    path = CATALOG_DIR / f"{model_id}.json"
    try:
        description = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelImportError(
            "Каталог моделей не установлен. Откройте локальное URDF/MJCF-описание."
        ) from exc
    return description


def inspect_description(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ModelImportError("Вставьте URDF, MJCF или YAML с robot.model.")
    if len(text.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ModelImportError("Описание превышает 2 МиБ.")
    if not text.lstrip("\ufeff \t\r\n").startswith("<"):
        # A strict small mapping, not a general interpretation of controller YAML.
        from robotci.config import _UniqueKeyLoader

        if re.search(r"[&*!]|\$\{|\$\(", text):
            raise ModelImportError("YAML-якоря, теги и подстановки здесь не поддержаны.")
        try:
            value = yaml.load(text, Loader=_UniqueKeyLoader)
        except (yaml.YAMLError, RecursionError) as exc:
            raise ModelImportError("Некорректный YAML конфигурации.") from exc
        robot = value.get("robot") if isinstance(value, dict) else None
        model_id = robot.get("model") if isinstance(robot, dict) else None
        if not isinstance(model_id, str) or model_id not in CATALOG:
            raise ModelImportError(
                "Из YAML без robot.model нельзя восстановить геометрию. Нужен URDF/MJCF."
            )
        model = catalog_model(model_id)
        model["identification"] = "declared_catalog"
        model["warnings"] = [
            *model["warnings"],
            "Модель выбрана через robot.model; управление YAML не применено.",
        ]
        return model
    root = _parse_xml(text.lstrip("\ufeff"))
    warnings = []
    if root.tag == "robot":
        nodes = _urdf(root, warnings)
        format_name, name = "URDF", root.get("name", "Робот URDF")
        warnings.append("Суставы показаны в допустимой опорной позе; это не симуляция.")
    elif root.tag == "mujoco":
        nodes = _mjcf(root, warnings)
        format_name, name = "MJCF", root.get("model", "Робот MJCF")
    else:
        raise ModelImportError("Нужен корневой элемент robot (URDF) или mujoco (MJCF).")
    _validate_tree(nodes)
    missing_geometry = sum(not n["visuals"] for n in nodes)
    if missing_geometry:
        warnings.append(
            f"У {missing_geometry} звеньев нет visual-геометрии; вместо оболочки показаны маркеры."
        )
    source_hash = hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()
    result = {
        "schema_version": 1,
        "format": format_name,
        "name": _name(name),
        "nodes": nodes,
        "source_sha256": source_hash,
        "visual_only": True,
        "simulation_ready": False,
        "classification": classify(nodes),
        "identification": "structural",
        "model_id": None,
        "warnings": list(dict.fromkeys(warnings)),
        "joint_count": sum(len(n["joints"]) for n in nodes),
        "link_count": len(nodes),
    }
    # A name alone never selects a catalog robot. Only exact pinned description bytes.
    for model_id in CATALOG:
        path = CATALOG_DIR / f"{model_id}.json"
        if path.is_file():
            candidate = catalog_model(model_id)
            if candidate.get("source_sha256") == source_hash:
                result["model_id"] = model_id
                result["identification"] = "exact_catalog_description"
                result["catalog_asset"] = candidate.get("catalog_asset")
                result["provenance"] = candidate.get("provenance")
                break
    return result
