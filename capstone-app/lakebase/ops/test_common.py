from _common import percentiles


def test_percentiles_basic():
    samples = [float(i) for i in range(1, 101)]  # 1..100 ms
    p = percentiles(samples, pcts=(50, 95, 99))
    assert p[50] == 50.0
    assert p[95] == 95.0
    assert p[99] == 99.0


def test_percentiles_single_sample():
    assert percentiles([7.0], pcts=(50, 95))[95] == 7.0
