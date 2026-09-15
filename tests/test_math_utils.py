from services.math_utils import compute_fibonacci

def test_fibonacci():
    assert compute_fibonacci(0) == 0
    assert compute_fibonacci(1) == 1
    assert compute_fibonacci(7) == 13
