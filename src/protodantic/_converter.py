"""Convert protobuf message classes to Pydantic models dynamically."""

from __future__ import annotations

import datetime
import enum
from typing import Any, Dict, List, Optional, Type

import pydantic
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from google.protobuf.descriptor import Descriptor, EnumDescriptor, FieldDescriptor

# google.api.field_behavior extension — value 2 means REQUIRED.
_FIELD_BEHAVIOR_REQUIRED = 2

try:
    from google.api import field_behavior_pb2

    _FIELD_BEHAVIOR_EXTENSION = field_behavior_pb2.field_behavior
except Exception:
    _FIELD_BEHAVIOR_EXTENSION = None

_PROTO_SCALAR_TYPE_MAP: dict[int, type] = {
    FieldDescriptor.TYPE_DOUBLE: float,
    FieldDescriptor.TYPE_FLOAT: float,
    FieldDescriptor.TYPE_INT64: int,
    FieldDescriptor.TYPE_UINT64: int,
    FieldDescriptor.TYPE_INT32: int,
    FieldDescriptor.TYPE_FIXED64: int,
    FieldDescriptor.TYPE_FIXED32: int,
    FieldDescriptor.TYPE_BOOL: bool,
    FieldDescriptor.TYPE_STRING: str,
    FieldDescriptor.TYPE_BYTES: bytes,
    FieldDescriptor.TYPE_UINT32: int,
    FieldDescriptor.TYPE_SFIXED32: int,
    FieldDescriptor.TYPE_SFIXED64: int,
    FieldDescriptor.TYPE_SINT32: int,
    FieldDescriptor.TYPE_SINT64: int,
}

_WELL_KNOWN_TYPE_MAP: dict[str, type] = {
    "google.protobuf.Struct": Dict[str, Any],
    "google.protobuf.Value": Any,
    "google.protobuf.ListValue": List[Any],
    "google.protobuf.Timestamp": datetime.datetime,
    "google.protobuf.Duration": datetime.timedelta,
    "google.protobuf.Any": Any,
    "google.protobuf.FieldMask": str,
    "google.protobuf.BoolValue": bool,
    "google.protobuf.BytesValue": bytes,
    "google.protobuf.DoubleValue": float,
    "google.protobuf.FloatValue": float,
    "google.protobuf.Int32Value": int,
    "google.protobuf.Int64Value": int,
    "google.protobuf.StringValue": str,
    "google.protobuf.UInt32Value": int,
    "google.protobuf.UInt64Value": int,
    "google.protobuf.Empty": type(None),
}

# Sentinel stored in the cache while a model is being built.
_IN_PROGRESS = object()


def _is_required(field: FieldDescriptor) -> bool:
    """Check if a field has google.api.field_behavior REQUIRED annotation."""
    if _FIELD_BEHAVIOR_EXTENSION is None:
        return False
    try:
        behaviors = field.GetOptions().Extensions[_FIELD_BEHAVIOR_EXTENSION]
        return _FIELD_BEHAVIOR_REQUIRED in behaviors
    except Exception:
        return False


def _enum_from_descriptor(
    enum_desc: EnumDescriptor,
    cache: dict[str, Any],
) -> type:
    """Create a StrEnum from a protobuf EnumDescriptor.

    Values are the SCREAMING_SNAKE_CASE names (e.g. ``ROLE_USER``),
    matching ProtoJSON enum serialisation conventions.
    """
    full_name = enum_desc.full_name
    cached = cache.get(full_name)
    if cached is not None:
        return cached

    members = {v.name: v.name for v in enum_desc.values}
    str_enum = enum.StrEnum(enum_desc.name, members)
    cache[full_name] = str_enum
    return str_enum


def model_from_proto(proto_cls: Type) -> Type[pydantic.BaseModel]:
    """Convert a protobuf message class to a Pydantic model.

    Recursively converts nested message types, repeated fields, and map fields.

    Features:
    - ProtoJSON compatible: camelCase aliases via ``alias_generator`` so models
      accept both ``snake_case`` and ``camelCase`` field names.
    - Required field detection: fields annotated with
      ``google.api.field_behavior = REQUIRED`` become mandatory Pydantic fields.
    - Enum support: proto enum fields become Python ``IntEnum`` types.
    - Well-known types (google.protobuf.Struct, Timestamp, etc.) are mapped to
      their natural Python equivalents.

    Args:
        proto_cls: A protobuf-generated message class (must have a DESCRIPTOR
            attribute).

    Returns:
        A dynamically created ``pydantic.BaseModel`` subclass with equivalent
        fields.
    """
    return _model_from_descriptor(proto_cls.DESCRIPTOR, cache={})


def _model_from_descriptor(
    descriptor: Descriptor,
    cache: dict[str, Any],
) -> type:
    full_name = descriptor.full_name

    if full_name in _WELL_KNOWN_TYPE_MAP:
        return _WELL_KNOWN_TYPE_MAP[full_name]

    cached = cache.get(full_name)
    if cached is _IN_PROGRESS:
        return Any
    if cached is not None:
        return cached

    cache[full_name] = _IN_PROGRESS

    field_definitions: dict[str, Any] = {}
    for field in descriptor.fields:
        python_type = _field_python_type(field, cache)
        if _is_required(field):
            field_definitions[field.name] = (python_type, ...)
        else:
            field_definitions[field.name] = (Optional[python_type], None)

    model = pydantic.create_model(
        descriptor.name,
        __config__=ConfigDict(
            alias_generator=to_camel,
            populate_by_name=True,
        ),
        **field_definitions,
    )
    cache[full_name] = model
    return model


def _field_python_type(field: FieldDescriptor, cache: dict[str, Any]) -> type:
    if (
        field.type == FieldDescriptor.TYPE_MESSAGE
        and field.message_type.GetOptions().map_entry
    ):
        key_type = _resolve_type(field.message_type.fields_by_name["key"], cache)
        value_type = _resolve_type(field.message_type.fields_by_name["value"], cache)
        return Dict[key_type, value_type]

    if field.is_repeated:
        return List[_resolve_type(field, cache)]

    return _resolve_type(field, cache)


def _resolve_type(field: FieldDescriptor, cache: dict[str, Any]) -> type:
    if field.type == FieldDescriptor.TYPE_MESSAGE:
        return _model_from_descriptor(field.message_type, cache)
    if field.type == FieldDescriptor.TYPE_ENUM:
        return _enum_from_descriptor(field.enum_type, cache)
    return _PROTO_SCALAR_TYPE_MAP.get(field.type, Any)
