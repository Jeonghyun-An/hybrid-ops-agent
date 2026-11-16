from hoa_agent.investigate import sole_exception


def test_a_single_wrapped_exception_is_unwrapped() -> None:
    cause = ValueError("schema")
    group = ExceptionGroup("tasks", [ExceptionGroup("inner", [cause])])

    assert sole_exception(group) is cause


def test_several_exceptions_stay_grouped() -> None:
    group = ExceptionGroup("tasks", [ValueError("a"), KeyError("b")])

    assert sole_exception(group) is group
