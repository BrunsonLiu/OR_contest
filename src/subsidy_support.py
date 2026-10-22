"""Exact threshold/excess rows; preserve the existing max(open_count-10, 0) policy."""


def subsidy_rows(count, trigger, excess, maximum, threshold=10):
    if not isinstance(maximum, int) or not isinstance(threshold, int) or not 1 <= threshold <= maximum:
        raise ValueError("invalid warehouse maximum or subsidy threshold")
    return [([count, trigger], [1.0, -maximum], "G", threshold-maximum),
            ([count, trigger], [1.0, -maximum], "L", threshold-1),
            ([excess, count], [1.0, -1.0], "G", -threshold),
            ([excess, trigger], [1.0, -maximum], "L", 0.0),
            ([excess, count, trigger], [1.0, -1.0, maximum], "L", maximum-threshold)]
