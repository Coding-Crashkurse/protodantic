"""Convert protobuf message classes to Pydantic models dynamically."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Type

import pydantic
from google.protobuf.descriptor import Descriptor, FieldDescriptor

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
    FieldDescriptor.TYPE_ENUM: int,
    FieldDescriptor.TYPE_SFIXED32: int,
    FieldDescriptor.TYPE_SFIXED64: int,
    FieldDescriptor.TYPE_SINT32: int,
    FieldDescriptor.TYPE_SINT64: int,
}

# Well-known types are mapped to Python equivalents before their descriptors
# are walked. This is necessary to avoid infinite recursion: google.protobuf.Struct
# and google.protobuf.Value are mutually recursive (Struct.fields is
# map<string, Value>; Value has a struct_value: Struct field).
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
# Encountering it during recursion means we have a user-defined cycle;
# we break it by returning Any for the back-reference.
_IN_PROGRESS = object()


def model_from_proto(proto_cls: Type) -> Type[pydantic.BaseModel]:
    """Convert a protobuf message class to a Pydantic model.

    Recursively converts nested message types, repeated fields, and map fields.
    All fields are optional with a default of None, matching proto3 semantics.

    Well-known types (google.protobuf.Struct, Timestamp, etc.) are mapped to
    their natural Python equivalents rather than being walked as descriptors.

    Args:
        proto_cls: A protobuf-generated message class (must have a DESCRIPTOR
            attribute).

    Returns:
        A dynamically created ``pydantic.BaseModel`` subclass with equivalent
        fields.

    Example::

        from my_proto_pb2 import MyMessage
        from protodantic import model_from_proto

        MyModel = model_from_proto(MyMessage)
        instance = MyModel(name="hello", value=42)
        print(instance.model_dump())
    """
    return _model_from_descriptor(proto_cls.DESCRIPTOR, cache={})


def _model_from_descriptor(
    descriptor: Descriptor,
    cache: dict[str, Any],
) -> type:
    full_name = descriptor.full_name

    # Intercept well-known types before walking their (potentially recursive) descriptors.
    if full_name in _WELL_KNOWN_TYPE_MAP:
        return _WELL_KNOWN_TYPE_MAP[full_name]

    cached = cache.get(full_name)
    if cached is _IN_PROGRESS:
        # Cycle detected in user-defined messages: break it with Any.
        return Any
    if cached is not None:
        return cached

    # Mark as in-progress before recursing into fields.
    cache[full_name] = _IN_PROGRESS

    field_definitions: dict[str, Any] = {}
    for field in descriptor.fields:
        python_type = _field_python_type(field, cache)
        field_definitions[field.name] = (Optional[python_type], None)

    model = pydantic.create_model(descriptor.name, **field_definitions)
    cache[full_name] = model
    return model


def _field_python_type(field: FieldDescriptor, cache: dict[str, Any]) -> type:
    # map<K, V> fields are represented as repeated synthetic message types
    # with map_entry=true on their descriptor options.
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
    return _PROTO_SCALAR_TYPE_MAP.get(field.type, Any)
