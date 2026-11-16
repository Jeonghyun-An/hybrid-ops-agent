from hoa_mcp.k8s_read.budget import MAX_OUTPUT_CHARS, clip, fit, serialized_chars
from hoa_mcp.k8s_read.models import EventList, EventSummary, PodLogs


def test_clip_keeps_short_text():
    assert clip("short", 10) == "short"


def test_clip_marks_cut_text_with_ellipsis_within_the_limit():
    clipped = clip("x" * 50, 10)
    assert len(clipped) == 10
    assert clipped.endswith("…")


def test_fit_leaves_a_small_result_untouched():
    logs = PodLogs(namespace="demo", pod="p", previous=False, lines=["one", "two"])
    assert fit(logs, "lines", drop="head") == logs


def test_fit_drops_oldest_log_lines_and_marks_truncated():
    lines = [f"{i:03d} " + "x" * 96 for i in range(300)]
    logs = PodLogs(namespace="demo", pod="p", previous=False, lines=lines)
    fitted = fit(logs, "lines", drop="head")
    assert serialized_chars(fitted) <= MAX_OUTPUT_CHARS
    assert fitted.truncated is True
    assert fitted.lines[-1] == lines[-1]
    assert fitted.lines[0] != lines[0]


def test_fit_drops_from_the_tail_for_newest_first_lists():
    events = [
        EventSummary(type="Warning", reason=f"R{i}", object="Pod/p", message="m" * 250, count=1)
        for i in range(100)
    ]
    fitted = fit(EventList(namespace="demo", events=events), "events", drop="tail")
    assert fitted.truncated is True
    assert fitted.events[0].reason == "R0"
    assert serialized_chars(fitted) <= MAX_OUTPUT_CHARS
