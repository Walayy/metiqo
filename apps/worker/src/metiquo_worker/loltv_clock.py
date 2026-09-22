"""Duration of the published LoLTV frame, excluding source-reported pauses."""


def frame_duration(events: object) -> int | None:
    if not isinstance(events, list):
        return None
    rows = [row for row in events if isinstance(row, dict)]
    if not rows or any(type(row.get("clock")) is not int for row in rows):
        return None
    rows.sort(key=lambda row: row["clock"])
    clocks = [row["clock"] for row in rows if row.get("type") != "PAUSE"]
    if not clocks:
        return None
    start, end = clocks[0], clocks[-1]
    intervals: list[tuple[int, int]] = []
    for index, row in enumerate(rows):
        if row.get("type") != "PAUSE":
            continue
        clock = row["clock"]
        if row.get("value") == "end":
            if clock > start and not any(a <= clock <= b for a, b in intervals):
                return None  # An unmatched resume cannot establish elapsed play time.
            continue
        if row.get("value") != "start":
            return None
        # The public Game component gives clock_end priority over the end event.
        # Observed end events can precede clock_end by one second.
        resume = row.get("clock_end")
        if resume is None:
            resume = next(
                (
                    following["clock"]
                    for following in rows[index + 1 :]
                    if following.get("type") == "PAUSE" and following.get("value") == "end"
                ),
                None,
            )
        if resume is None:
            # An ongoing pause freezes this frame at its published start. Never
            # extrapolate from retrieval time or from the user's wall clock.
            end = min(end, clock)
            break
        if type(resume) is not int or resume < clock:
            return None
        intervals.append((clock, resume))
    if end < start:
        return None
    # Match the public Game component's cumulative correction, including
    # overlapping source entries (observed on Pyramid–LODIS game 1). Merging
    # those intervals would produce a different clock from the published UI.
    paused = sum(max(0, min(end, right) - max(start, left)) for left, right in intervals)
    return int(max(0, (end - start - paused) // 1000))
