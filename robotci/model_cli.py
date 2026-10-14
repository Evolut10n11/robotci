"""Read-only, offline CLI inspection of robot descriptions and reference models."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from robotci.model_import import (
    CATALOG,
    MAX_DESCRIPTION_BYTES,
    ModelImportError,
    catalog_model,
    inspect_description,
)

_KINDS = {
    "quadruped": "четвероногий робот",
    "humanoid": "гуманоид",
    "manipulator": "манипулятор",
    "wheeled": "колёсный робот",
    "unknown": "не определён",
}
_CONFIDENCE = {"high": "высокая", "medium": "средняя", "low": "низкая"}


class ModelFileError(ModelImportError):
    """The input is not a bounded UTF-8 regular file."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json(payload: dict[str, Any]) -> None:
    # Plain echo keeps redirected stdout free from styling and line wrapping.
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def _error(kind: str, code: str, message: str, *, json_output: bool) -> NoReturn:
    if json_output:
        _json(
            {
                "schema_version": 1,
                "kind": kind,
                "scope": "static_reference",
                "mesh_files_checked": False,
                "error": {"code": code, "message": message},
            }
        )
    else:
        typer.echo(f"Ошибка описания робота: {message}", err=True)
    raise typer.Exit(code=3)


model_app = typer.Typer(
    help="Офлайн-инспекция URDF/MJCF и каталога опорных моделей, без запуска робота.",
    no_args_is_help=True,
)


def _read_description(path: Path) -> tuple[bytes, str]:
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ModelFileError("not_regular_file", "Нужен обычный файл URDF, MJCF или YAML.")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ModelFileError("not_regular_file", "Нужен обычный файл описания.")
            if info.st_size > MAX_DESCRIPTION_BYTES:
                raise ModelFileError("description_too_large", "Описание превышает 2 МиБ.")
            raw = source.read(MAX_DESCRIPTION_BYTES + 1)
    except OSError as exc:
        raise ModelFileError("io_error", f"Не удалось прочитать файл {path}: {exc}") from exc
    if len(raw) > MAX_DESCRIPTION_BYTES:
        raise ModelFileError("description_too_large", "Описание превышает 2 МиБ.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ModelFileError(
            "invalid_encoding", "Описание должно быть в UTF-8; BOM UTF-8 допустим."
        ) from exc
    return raw, text


@model_app.command("list")
def list_models(
    json_output: Annotated[
        bool, typer.Option("--json", help="Вывести только JSON, включая ошибки.")
    ] = False,
) -> None:
    """Показать встроенные модели Go2, G1 и Panda с закреплёнными источниками."""
    models = []
    try:
        for model_id, metadata in CATALOG.items():
            model = catalog_model(model_id)
            models.append(
                {
                    "model_id": model_id,
                    "label": metadata["label"],
                    **{
                        key: model[key]
                        for key in (
                            "name",
                            "format",
                            "classification",
                            "link_count",
                            "joint_count",
                            "provenance",
                            "catalog_asset",
                            "geometry",
                        )
                    },
                }
            )
    except (ModelImportError, OSError, UnicodeError, KeyError, TypeError) as exc:
        _error("robot_model_catalog", "catalog_error", str(exc), json_output=json_output)
    if json_output:
        _json(
            {
                "schema_version": 1,
                "kind": "robot_model_catalog",
                "scope": "static_reference",
                "offline": True,
                "mesh_files_checked": False,
                "models": models,
            }
        )
        return
    typer.echo("Локальный каталог опорных моделей; загрузка из сети не требуется.")
    for model in models:
        provenance = model["provenance"]
        kind = model["classification"]["kind"]
        typer.echo(f"\n{model['label']} ({model['model_id']}): {_KINDS.get(kind, kind)}")
        typer.echo(f"  Звеньев: {model['link_count']}; суставов: {model['joint_count']}")
        typer.echo(f"  Источник: {provenance['repository']}/{provenance['file']}")
        typer.echo(f"  Ревизия: {provenance['revision']}")
    typer.echo("\nscope=static_reference; mesh_files_checked=false")
    typer.echo("Каталог описывает опорную геометрию. Управление и динамика не проверялись.")


@model_app.command("inspect")
def inspect_model(
    file: Annotated[
        Path, typer.Argument(help="Файл URDF, MJCF или YAML с robot.model (UTF-8, до 2 МиБ).")
    ],
    json_output: Annotated[
        bool, typer.Option("--json", help="Вывести только JSON, включая ошибки.")
    ] = False,
) -> None:
    """Прочитать описание модели. Это не валидация сценариев robotci.yaml."""
    try:
        raw, text = _read_description(file)
        description = inspect_description(text)
    except ModelFileError as exc:
        _error("robot_model_inspection", exc.code, str(exc), json_output=json_output)
    except (ModelImportError, OSError, UnicodeError) as exc:
        _error("robot_model_inspection", "invalid_description", str(exc), json_output=json_output)
    payload = {
        "schema_version": 1,
        "kind": "robot_model_inspection",
        "scope": "static_reference",
        "mesh_files_checked": False,
        "source_file": {
            "path": str(file),
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "description": description,
    }
    if json_output:
        _json(payload)
        return
    classification = description["classification"]
    kind = classification["kind"]
    confidence = classification["confidence"]
    typer.echo(f"Модель: {description['name']}; формат: {description['format']}")
    typer.echo(
        f"Тип: {_KINDS.get(kind, kind)}; уверенность: {_CONFIDENCE.get(confidence, confidence)}"
    )
    typer.echo(f"model_id: {description['model_id'] or 'не установлен'}")
    typer.echo(f"Звеньев: {description['link_count']}; суставов: {description['joint_count']}")
    typer.echo(f"SHA256 файла: {payload['source_file']['sha256']}")
    typer.echo("scope=static_reference; mesh_files_checked=false")
    typer.echo("Файлы мешей не читались. Динамика, управление и сценарии не проверялись.")
    for warning in description["warnings"]:
        typer.echo(f"Предупреждение: {warning}")
