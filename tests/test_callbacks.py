"""Every callback schema must survive a pack/unpack round trip.

Regression guard. aiogram packs an empty string and unpacks it as ``None``, so
a ``str`` field with an empty default fails validation on the way back in and
the update is dropped before any handler sees it -- the button silently does
nothing. This caught exactly that on Check Payment, SMM search, the settings
toggle, rental pagination and most of the admin panel.
"""

import inspect

import pytest

from app.bot import callbacks as cb

#: Every CallbackData subclass the bot defines.
SCHEMAS = [
    value
    for _, value in inspect.getmembers(cb, inspect.isclass)
    if issubclass(value, cb.CallbackData) and value is not cb.CallbackData
]


def test_every_schema_is_covered():
    assert len(SCHEMAS) >= 14, "a new callback schema is not being round-trip tested"


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_defaults_round_trip(schema):
    """Constructed with only its required fields, a callback must survive."""
    required = {
        name: _sample(field.annotation)
        for name, field in schema.model_fields.items()
        if field.is_required()
    }
    packed = schema(**required).pack()
    restored = schema.unpack(packed)

    for name, value in required.items():
        assert getattr(restored, name) == value


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_optional_string_fields_are_nullable(schema):
    """A ``str`` field with an empty default is the shape of the bug."""
    for name, field in schema.model_fields.items():
        if field.is_required():
            continue
        if field.default == "":
            pytest.fail(
                f"{schema.__name__}.{name} defaults to '' — declare it "
                f"'str | None = None' or the callback will be dropped"
            )


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_packed_data_fits_telegram_limit(schema):
    """Telegram rejects callback data over 64 bytes."""
    values = {
        name: _sample(field.annotation, long=True)
        for name, field in schema.model_fields.items()
    }
    packed = schema(**values).pack()
    assert len(packed.encode()) <= 64, f"{schema.__name__} packs to {len(packed)} bytes"


def _sample(annotation, long: bool = False):
    if annotation is int:
        return 999_999 if long else 1
    return ("x" * 12) if long else "sample"
