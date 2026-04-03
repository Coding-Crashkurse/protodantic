"""Tests for protodantic.model_from_proto using a2a_pb2 types."""

import datetime
import enum
from typing import Any, Union, get_args, get_origin

import pydantic
import pytest

import a2a_pb2
from protodantic import model_from_proto


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unwrap_optional(tp: type) -> type:
    """Extract T from Optional[T] (Union[T, None]), else return tp unchanged."""
    if get_origin(tp) is Union:
        non_none = [a for a in get_args(tp) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return tp


def _inner(model: type[pydantic.BaseModel], field_name: str) -> type:
    """Return the unwrapped type annotation for a named field."""
    annotation = model.model_fields[field_name].annotation
    return _unwrap_optional(annotation)


# ---------------------------------------------------------------------------
# Basic model structure
# ---------------------------------------------------------------------------

class TestModelBasics:
    def test_returns_pydantic_base_model_subclass(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert issubclass(Model, pydantic.BaseModel)

    def test_model_name_matches_proto_descriptor_name(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert Model.__name__ == "AuthenticationInfo"

    def test_all_expected_fields_present(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert set(Model.model_fields) == {"scheme", "credentials"}

    def test_optional_fields_default_to_none(self):
        # Non-required proto3 fields default to None.
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert Model.model_fields["credentials"].default is None

    def test_required_fields_have_no_default(self):
        # Fields with google.api.field_behavior = REQUIRED are mandatory.
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert Model.model_fields["scheme"].is_required()

    def test_independent_calls_produce_equivalent_field_sets(self):
        Model1 = model_from_proto(a2a_pb2.AuthenticationInfo)
        Model2 = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert set(Model1.model_fields) == set(Model2.model_fields)


# ---------------------------------------------------------------------------
# Scalar field type mapping
# ---------------------------------------------------------------------------

class TestScalarFieldTypes:
    def test_string_fields(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        assert _inner(Model, "scheme") is str
        assert _inner(Model, "credentials") is str

    def test_bool_fields(self):
        Model = model_from_proto(a2a_pb2.AgentCapabilities)
        assert _inner(Model, "streaming") is bool
        assert _inner(Model, "push_notifications") is bool

    def test_int_field(self):
        Model = model_from_proto(a2a_pb2.GetTaskRequest)
        assert _inner(Model, "history_length") is int

    def test_bytes_field(self):
        Model = model_from_proto(a2a_pb2.Part)
        assert _inner(Model, "raw") is bytes


# ---------------------------------------------------------------------------
# Enum field type mapping
# ---------------------------------------------------------------------------

class TestEnumFields:
    def test_proto_enum_maps_to_str_enum(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        inner = _inner(Model, "state")
        assert issubclass(inner, enum.StrEnum)
        assert inner.__name__ == "TaskState"

    def test_enum_has_expected_members(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        TaskState = _inner(Model, "state")
        assert TaskState.TASK_STATE_UNSPECIFIED == "TASK_STATE_UNSPECIFIED"
        assert TaskState.TASK_STATE_SUBMITTED == "TASK_STATE_SUBMITTED"
        assert TaskState.TASK_STATE_WORKING == "TASK_STATE_WORKING"
        assert TaskState.TASK_STATE_COMPLETED == "TASK_STATE_COMPLETED"

    def test_role_enum(self):
        Model = model_from_proto(a2a_pb2.Message)
        Role = _inner(Model, "role")
        assert issubclass(Role, enum.StrEnum)
        assert Role.ROLE_USER == "ROLE_USER"
        assert Role.ROLE_AGENT == "ROLE_AGENT"

    def test_enum_value_accepted_by_model(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        TaskState = _inner(Model, "state")
        instance = Model(state=TaskState.TASK_STATE_WORKING)
        assert instance.state == TaskState.TASK_STATE_WORKING

    def test_enum_string_value_accepted(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        instance = Model(state="TASK_STATE_WORKING")
        assert instance.state == "TASK_STATE_WORKING"


# ---------------------------------------------------------------------------
# Required field validation
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_required_field_raises_on_missing(self):
        Model = model_from_proto(a2a_pb2.Task)
        with pytest.raises(pydantic.ValidationError):
            Model()  # id and status are REQUIRED

    def test_required_field_is_required(self):
        Model = model_from_proto(a2a_pb2.Task)
        assert Model.model_fields["id"].is_required()
        assert Model.model_fields["status"].is_required()

    def test_non_required_field_is_optional(self):
        Model = model_from_proto(a2a_pb2.Task)
        assert not Model.model_fields["context_id"].is_required()
        assert Model.model_fields["context_id"].default is None

    def test_message_required_fields(self):
        Model = model_from_proto(a2a_pb2.Message)
        assert Model.model_fields["message_id"].is_required()
        assert Model.model_fields["role"].is_required()
        assert Model.model_fields["parts"].is_required()
        assert not Model.model_fields["context_id"].is_required()

    def test_required_validation_catches_empty_input(self):
        Model = model_from_proto(a2a_pb2.SendMessageRequest)
        with pytest.raises(pydantic.ValidationError):
            Model()  # message is REQUIRED


# ---------------------------------------------------------------------------
# ProtoJSON / camelCase alias support
# ---------------------------------------------------------------------------

class TestProtoJsonAliases:
    def test_model_accepts_camel_case_keys(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        instance = Model.model_validate({"scheme": "Bearer", "credentials": "tok"})
        assert instance.scheme == "Bearer"

    def test_model_accepts_snake_case_keys(self):
        Model = model_from_proto(a2a_pb2.SendMessageConfiguration)
        instance = Model(accepted_output_modes=["text/plain"])
        assert instance.accepted_output_modes == ["text/plain"]

    def test_model_dump_by_alias_produces_camel_case(self):
        Model = model_from_proto(a2a_pb2.SendMessageConfiguration)
        instance = Model(accepted_output_modes=["text/plain"], return_immediately=True)
        dumped = instance.model_dump(by_alias=True)
        assert "acceptedOutputModes" in dumped
        assert "returnImmediately" in dumped

    def test_model_validate_camel_case_json(self):
        Model = model_from_proto(a2a_pb2.TaskPushNotificationConfig)
        data = {"url": "https://example.com", "taskId": "t-1"}
        instance = Model.model_validate(data)
        assert instance.task_id == "t-1"
        assert instance.url == "https://example.com"

    def test_roundtrip_camel_case(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        data = {"scheme": "Bearer", "credentials": "tok123"}
        instance = Model.model_validate(data)
        dumped = instance.model_dump(by_alias=True)
        restored = Model.model_validate(dumped)
        assert restored.scheme == "Bearer"
        assert restored.credentials == "tok123"


# ---------------------------------------------------------------------------
# Repeated fields
# ---------------------------------------------------------------------------

class TestRepeatedFields:
    def test_repeated_scalar_becomes_list_of_scalar(self):
        Model = model_from_proto(a2a_pb2.AgentSkill)
        inner = _inner(Model, "tags")
        assert get_origin(inner) is list
        assert get_args(inner) == (str,)

    def test_repeated_message_becomes_list_of_pydantic_model(self):
        Model = model_from_proto(a2a_pb2.Task)
        inner = _inner(Model, "artifacts")
        assert get_origin(inner) is list
        (item_type,) = get_args(inner)
        assert issubclass(item_type, pydantic.BaseModel)
        assert item_type.__name__ == "Artifact"

    def test_repeated_message_item_has_expected_fields(self):
        Model = model_from_proto(a2a_pb2.Task)
        ArtifactModel = get_args(_inner(Model, "artifacts"))[0]
        assert "artifact_id" in ArtifactModel.model_fields
        assert "parts" in ArtifactModel.model_fields


# ---------------------------------------------------------------------------
# Nested messages
# ---------------------------------------------------------------------------

class TestNestedMessages:
    def test_nested_message_field_becomes_pydantic_model(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        inner = _inner(Model, "message")
        assert issubclass(inner, pydantic.BaseModel)
        assert inner.__name__ == "Message"

    def test_nested_model_carries_its_own_fields(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        MessageModel = _inner(Model, "message")
        assert "role" in MessageModel.model_fields
        assert "parts" in MessageModel.model_fields

    def test_three_levels_of_nesting(self):
        Model = model_from_proto(a2a_pb2.SendMessageRequest)
        ConfigModel = _inner(Model, "configuration")
        PushModel = _inner(ConfigModel, "task_push_notification_config")
        AuthModel = _inner(PushModel, "authentication")
        assert AuthModel.__name__ == "AuthenticationInfo"
        assert "scheme" in AuthModel.model_fields


# ---------------------------------------------------------------------------
# Map fields
# ---------------------------------------------------------------------------

class TestMapFields:
    def test_map_str_str_becomes_dict_str_str(self):
        Model = model_from_proto(a2a_pb2.AuthorizationCodeOAuthFlow)
        inner = _inner(Model, "scopes")
        assert get_origin(inner) is dict
        assert get_args(inner) == (str, str)

    def test_map_str_message_becomes_dict_str_model(self):
        Model = model_from_proto(a2a_pb2.AgentCard)
        inner = _inner(Model, "security_schemes")
        assert get_origin(inner) is dict
        key_type, value_type = get_args(inner)
        assert key_type is str
        assert issubclass(value_type, pydantic.BaseModel)
        assert value_type.__name__ == "SecurityScheme"

    def test_map_str_list_message_becomes_dict_str_model(self):
        Model = model_from_proto(a2a_pb2.SecurityRequirement)
        inner = _inner(Model, "schemes")
        assert get_origin(inner) is dict
        key_type, value_type = get_args(inner)
        assert key_type is str
        assert issubclass(value_type, pydantic.BaseModel)
        assert value_type.__name__ == "StringList"


# ---------------------------------------------------------------------------
# Well-known type mapping
# ---------------------------------------------------------------------------

class TestWellKnownTypes:
    def test_struct_field_becomes_dict_str_any(self):
        Model = model_from_proto(a2a_pb2.Task)
        inner = _inner(Model, "metadata")
        assert get_origin(inner) is dict
        key_type, value_type = get_args(inner)
        assert key_type is str
        assert value_type is Any

    def test_timestamp_field_becomes_datetime(self):
        Model = model_from_proto(a2a_pb2.TaskStatus)
        assert _inner(Model, "timestamp") is datetime.datetime

    def test_no_recursion_error_from_struct_value_cycle(self):
        Model = model_from_proto(a2a_pb2.AgentExtension)
        assert "params" in Model.model_fields

    def test_no_recursion_error_on_send_message_request(self):
        Model = model_from_proto(a2a_pb2.SendMessageRequest)
        assert Model is not None
        assert "metadata" in Model.model_fields

    def test_no_recursion_error_on_agent_card(self):
        Model = model_from_proto(a2a_pb2.AgentCard)
        assert Model is not None


# ---------------------------------------------------------------------------
# Model usability
# ---------------------------------------------------------------------------

class TestModelUsability:
    def test_instantiation_with_required_fields_only(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        instance = Model(scheme="Bearer")
        assert instance.scheme == "Bearer"
        assert instance.credentials is None

    def test_instantiation_with_all_fields(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        instance = Model(scheme="Bearer", credentials="tok123")
        assert instance.scheme == "Bearer"
        assert instance.credentials == "tok123"

    def test_model_dump_returns_all_fields(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        instance = Model(scheme="Bearer")
        assert instance.model_dump() == {"scheme": "Bearer", "credentials": None}

    def test_model_dump_json(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        instance = Model(scheme="Bearer", credentials="tok")
        json_str = instance.model_dump_json()
        assert "Bearer" in json_str
        assert "tok" in json_str

    def test_model_json_schema(self):
        Model = model_from_proto(a2a_pb2.AuthenticationInfo)
        schema = Model.model_json_schema()
        assert "properties" in schema
        assert "scheme" in schema["properties"]
        assert "credentials" in schema["properties"]

    def test_nested_model_instantiation(self):
        TaskStatusModel = model_from_proto(a2a_pb2.TaskStatus)
        instance = TaskStatusModel(state="TASK_STATE_WORKING")
        assert instance.state == "TASK_STATE_WORKING"
        assert instance.message is None
        assert instance.timestamp is None

    def test_complex_model_json_schema_does_not_raise(self):
        Model = model_from_proto(a2a_pb2.AgentCard)
        schema = Model.model_json_schema()
        assert "properties" in schema
