import pytest
from scripts.auto_validate import Validator


def test_numeric_validation():
    cols = {
        "0": {"name": "id", "type": "numeric", "max_length": 10},
        "1": {"name": "amount", "type": "numeric", "max_length": 10},
    }
    v = Validator(cols, header_row=0)

    # valid row
    row = ["1", "123.45"]
    assert v.validate_row(row, 1) == []

    # non-numeric
    row = ["a", "12x"]
    errs = v.validate_row(row, 1)
    assert any("not numeric" in e for e in errs)


def test_length_and_column_count():
    cols = {"0": {"name": "code", "type": "string", "max_length": 3}}
    v = Validator(cols, header_row=0)

    # column count mismatch
    errs = v.validate_row(["a", "b"], 1)
    assert any("Column count mismatch" in e for e in errs)

    # length overflow
    errs = v.validate_row(["toolong"], 1)
    assert any("length overflow" in e for e in errs)
