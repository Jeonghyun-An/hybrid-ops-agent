from collections.abc import Callable

import pytest

from hoa_eval.agent import AgentReport
from hoa_eval.scenario import Scenario
from hoa_eval.scoring import quote_found, score

OUTPUT = '{"waiting_message": "Back-off pulling image \\"hoa-demo:0.1.0-missing\\"", "count": 3}'


@pytest.mark.parametrize(
    "quote",
    [
        'Back-off pulling image "hoa-demo:0.1.0-missing"',
        'waiting_message: "Back-off pulling image "hoa-demo:0.1.0-missing""',
        "Back-off   pulling image hoa-demo:0.1.0-missing.",
    ],
)
def test_quotes_match_despite_json_escapes_quotes_and_spacing(quote: str) -> None:
    assert quote_found(quote, [OUTPUT]) is True


@pytest.mark.parametrize("quote", ["Back-off pulling image nginx:1.0", "", '""'])
def test_made_up_or_empty_quotes_do_not_match(quote: str) -> None:
    assert quote_found(quote, [OUTPUT]) is False


def test_correct_diagnosis_scores_label_target_and_quotes(
    make_report: Callable[..., AgentReport], image_pull: Scenario
) -> None:
    result = score(image_pull.expected, make_report(target="Demo/orders"))

    assert result.label_correct is True
    assert result.target_correct is True
    assert (result.quotes, result.quotes_found) == (1, 1)
    assert (result.tool_calls, result.tool_errors, result.invalid_tool_calls) == (2, 1, 1)
    assert (result.input_tokens, result.elapsed_seconds) == (4_000, 6.5)


def test_quotes_from_failed_tool_calls_do_not_count(
    make_report: Callable[..., AgentReport], image_pull: Scenario
) -> None:
    result = score(image_pull.expected, make_report(quotes=("pod x not found",)))

    assert result.quotes_found == 0


def test_wrong_label_and_target_are_marked(
    make_report: Callable[..., AgentReport], bad_config: Scenario
) -> None:
    result = score(bad_config.expected, make_report())

    assert result.label_correct is False
    assert result.target_correct is False
