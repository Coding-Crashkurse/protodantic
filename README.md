# protodantic

A type adaptor which allows protobuf generated types to be used as Pydantic models.

## Installation

```bash
pip install protodantic
```

## Usage

Given a protobuf definition like this:

```proto
message Address {
  string street = 1;
  string city = 2;
  string country = 3;
}

message Person {
  string name = 1;
  int32 age = 2;
  Address address = 3;
  repeated string emails = 4;
}
```

Pass the generated class to `model_from_proto` to get a fully usable Pydantic model:

```python
from protodantic import model_from_proto
from my_proto_pb2 import Person

PersonModel = model_from_proto(Person)

# Instantiate and validate
person = PersonModel(
    name="Alice",
    age=30,
    emails=["alice@example.com", "alice@work.com"],
)

# Serialise to dict or JSON
person.model_dump()
# {'name': 'Alice', 'age': 30, 'address': None, 'emails': ['alice@example.com', 'alice@work.com']}

person.model_dump_json()
# '{"name":"Alice","age":30,"address":null,"emails":["alice@example.com","alice@work.com"]}'

# Generate a JSON schema
PersonModel.model_json_schema()
# {'properties': {'name': ..., 'age': ..., 'address': ..., 'emails': ...}, ...}
```

Nested messages are converted recursively — `address` above becomes its own
`Pydantic` model with `street`, `city`, and `country` fields.

## Field type mapping

| Protobuf | Python |
|---|---|
| `string` | `str` |
| `bool` | `bool` |
| `int32`, `int64`, `uint32`, `uint64`, … | `int` |
| `float`, `double` | `float` |
| `bytes` | `bytes` |
| `enum` | `int` |
| `message Foo` | Pydantic model (recursively converted) |
| `repeated T` | `List[T]` |
| `map<K, V>` | `Dict[K, V]` |
| `google.protobuf.Struct` | `Dict[str, Any]` |
| `google.protobuf.Timestamp` | `datetime.datetime` |
| `google.protobuf.Duration` | `datetime.timedelta` |
| `google.protobuf.Value` | `Any` |
| `google.protobuf.ListValue` | `List[Any]` |
| `google.protobuf.Any` | `Any` |

All fields are `Optional` with a default of `None`, matching proto3 semantics.
